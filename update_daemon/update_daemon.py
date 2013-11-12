# !/usr/bin/env python

''' 
  update_daemon - Provides base update daemon functionality.
  Author - Shal Dengeki <shaldengeki@gmail.com>
  REQUIRES - configobj, filelock, DbConn, MailServer, albatross
'''

import configobj
import httplib

import logging
import logging.handlers

import time
import traceback

import filelock
import DbConn
import MailServer
import albatross

import update_modules

# causes httplib to return the partial response from a server in case the read fails to be complete.
def patch_http_response_read(func):
    def inner(*args):
        try:
            return func(*args)
        except httplib.IncompleteRead, e:
            return e.partial
    return inner
httplib.HTTPResponse.read = patch_http_response_read(httplib.HTTPResponse.read)

class UpdateDaemon(object):
  """
    Generic update daemon class.
  """

  def __init__(self, name, modules, config_file=None):
    """
      Initializes update daemon.
      Takes module for modules.
      Takes string file path for config_file.
    """
    self.name = name
    self.modules = modules
    self.config_file = unicode(config_file)
    self.load_config()
    self.info = {}
    self.etiUp = True

  def load_config(self, config_file=None):
    if config_file is not None:
      self.config_file = unicode(config_file)

    self.config = configobj.ConfigObj(self.config_file)

    # Logging settings.
    self.log = logging.getLogger(self.name + ".info")
    self.log.setLevel(int(getattr(logging, self.config['LOG']['min_level'])))

    # close all logging handlers.
    for handler in self.log.handlers:
      handler.close()
    self.log.handlers = []

    # add a syslog handler.
    handler = logging.handlers.SysLogHandler(facility=logging.handlers.SysLogHandler.LOG_DAEMON, address='/dev/log')
    self.log.addHandler(handler)

    # Mail settings.
    if 'MAIL' in self.config:
      self.mail = MailServer.MailServer(smtp_host=self.config['MAIL']['smtp_host'],
                                        smtp_port=int(self.config['MAIL']['smtp_port']),
                                        imap_host=self.config['MAIL']['imap_host'],
                                        username=self.config['MAIL']['username'], 
                                        password=self.config['MAIL']['password'])
      if self.config['MAIL']['ccs'] == '':
        self.config['MAIL']['ccs'] = []

    # Database settings.
    if 'DB' in self.config:
      self.reset_dbs()

    if 'ETI' in self.config:
      # ETI settings.
      # see if the cached cookie string works.
      with open(self.config['ETI']['cookie_file'], 'r') as cookie_file:
        try:
          self.eti = albatross.Connection(cookieString=cookie_file.read().strip(),
                                          cookieFile = self.config['ETI']['cookie_file'],
                                          loginSite=getattr(albatross, self.config['ETI']['site']))
        except albatross.UnauthorizedError:
          # log in using username.
          try:
            # acquire a lock on the cookie file so only one auth attempt happens at once.
            with filelock.FileLock(self.config['ETI']['cookie_file'], timeout=0) as lock:
              self.eti = albatross.Connection(username=self.config['ETI']['username'],
                                              password=self.config['ETI']['password'],
                                              loginSite=getattr(albatross, self.config['ETI']['site']))
              self.config['ETI']['cookie_string'] = unicode(self.eti.cookieString)

              # write the new cookie string to the cookie file.
              with open(self.config['ETI']['cookie_file'], 'w') as cookie_file:
                cookie_file.write(self.config['ETI']['cookie_string'].encode('utf-8'))
          except filelock.FileLockException:
            # another process is authing. reload cookie string until it's different.
            if 'cookie_string' not in self.config['ETI']:
              self.config['ETI']['cookie_string'] = u""
            self.log.warning("Another process has locked the cookie string file. Refreshing cookie string file until a new one is loaded.")
            while True:
              with open(self.config['ETI']['cookie_file'], 'r') as cookie_string_file:
                new_cookie_string = unicode(cookie_string_file.read().strip())
                if new_cookie_string != self.config['ETI']['cookie_string']:
                  self.config['ETI']['cookie_string'] = new_cookie_string
                  break

          # reset our eti connection.
          self.eti = albatross.Connection(cookieString=self.config['ETI']['cookie_string'],
                                          cookieFile=self.config['ETI']['cookie_file'],
                                          loginSite=getattr(albatross, self.config['ETI']['site']))

      if not self.eti:
        self.log.critical("Unable to log into ETI with stored credentials.")
        return
    else:
      self.eti = None

  def preload(self):
    """
      Tasks to be run after initialization, but before updating.
      Fetch additional daemon-specific config / timing info and store it in self.info here.
    """
    pass

  def update(self):
    """
      Inner loop of daemon.
    """
    # Reload the module functions in case they've changed.
    reload(self.modules)

    # Now call all module functions and set the last link and topicIDs to be whatever these module functions return.
    modules = self.modules.Modules(self)
    modules.update()

  def flush_dbs(self):
    for db in self.dbs:
      self.dbs[db].commit()

  def clear_dbs(self):
    for db in self.dbs:
      self.dbs[db].clearParams()

  def empty_dbs(self):
    # clear parameters and commit all db connections.
    self.clear_dbs()
    self.flush_dbs()

  def set_dbs(self):
    # establish database connections with the configurations in self.config['DB']
    if not hasattr(self, 'dbs') or self.dbs is None:
      self.dbs = {}

    for connection_name in self.config['DB']:
      db_info = self.config['DB'][connection_name]
      self.dbs[connection_name] = DbConn.DbConn(db_info['username'], db_info['password'], db_info['name'])

  def close_dbs(self):
    # close all database connections that we can.
    if hasattr(self, 'dbs') and self.dbs is not None:
      for connection_name in self.dbs:
        try:
          self.dbs[connection_name].close()
        except:
          # if we can't cleanly end the connection, pass over it.
          pass
    self.dbs = {}

  def reset_dbs(self):
    # close all database connections and establish new ones.
    self.close_dbs()
    self.set_dbs()



  def run(self):
    """
      Runs the update daemon indefinitely.
    """
    try:
      self.preload()
      while 1:
        try:
          self.update()
          if self.eti and not self.etiUp and self.eti.etiUp():
            self.log.debug("ETI seems to have recovered. Setting db index.")
            self.etiUp = True
            self.dbs['llBackup'].table('indices').set(value=1).where(name='eti_up').update()
        except albatross.PageLoadError:
          if self.eti and self.etiUp and not self.eti.etiUp():
            self.log.debug("ETI seems to be down. Setting db index and retrying.")
            self.etiUp = False
            self.clear_dbs()
            self.dbs['llBackup'].table('indices').set(value=0).where(name='eti_up').update()
        except:
          self.log.error("Error: " + str(traceback.format_exc()))
          self.mail.send(toEmail=self.config['MAIL']['destination'], ccEmail=self.config['MAIL']['ccs'], subject=self.name + ": Error (recoverable)", body=self.name + """ has suffered an exception but will continue to run.\nError:\n""" + str(traceback.format_exc()))
          self.clear_dbs()
        time.sleep(int(self.config['loop_interval']))
    except albatross.PageLoadError:
      if self.eti and self.etiUp and not self.eti.etiUp():
        self.log.debug("ETI seems to be down. Setting db index and exiting.")
        self.etiUp = False
        self.clear_dbs()
        self.dbs['llBackup'].table('indices').set(value=0).where(name='eti_up').update()
    except:
      self.log.critical(str(traceback.format_exc()))
      self.mail.send(toEmail=self.config['MAIL']['destination'], ccEmail=self.config['MAIL']['ccs'], subject=self.name + ": Error (unrecoverable)", body=self.name + """ has suffered an exception and needs to exit.\nError:\n""" + str(traceback.format_exc()))