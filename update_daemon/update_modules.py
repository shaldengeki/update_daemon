# !/usr/bin/env python

''' 
  update_modules - Provides base update_daemon module functionality.
  Author - Shal Dengeki <shaldengeki@gmail.com>
  REQUIRES - albatross
'''

import calendar
import datetime
import traceback

import pytz
import albatross

class Modules(object):
  def __init__(self, daemon):
    self.daemon = daemon
    self.dbs = self.daemon.dbs
    self.config = self.daemon.config
    self.info = self.daemon.info

    # list of functions that should be run upon update(), in the order they should be run.
    self.update_functions = [self.touchTimeStamp]

  def update(self):
    '''
    Runs all desired update functions in the order that they should be executed.
    '''
    for function in self.update_functions:
      try:
        function()
        self.daemon.flush_dbs()
      except albatross.PageLoadError:
        if self.daemon.eti and self.daemon.etiUp and not self.daemon.eti.etiUp():
          self.daemon.log.debug("ETI seems to be down. Setting db index and retrying.")
          self.daemon.etiUp = False
          self.dbs['llBackup'].table('indices').set(value=0).where(name='eti_up').update()
          self.daemon.reset_dbs()
      except:
        exception_message_parts = [str(traceback.format_exc())]
        if hasattr(self, 'dbs'):
          for db_name in self.dbs:
            if self.dbs[db_name]._table is not None:
              exception_message_parts.append(self.dbs[db_name].queryString())
              if self.dbs[db_name]._params is not None:
                exception_params = filter(lambda x: x is not None, self.dbs[db_name]._params)
                exception_message_parts.append("Parameters:")
                exception_message_parts.append(",".join(str(x) for x in exception_params))
        exception_message = "\n".join(exception_message_parts)
        self.daemon.log.error("Error: " + exception_message)
        self.daemon.mail.send(toEmail=self.config['MAIL']['destination'], ccEmail=self.config['MAIL']['ccs'], subject=self.daemon.name + ": Error (recoverable)", body=self.daemon.name + """ has suffered an exception in """ + function.__name__ + """() but will continue to run.\nError:\n""" + exception_message)
        self.daemon.reset_dbs()

  def touchTimeStamp(self):
    '''
    Updates the last-active timestamp corresponding to this bot.
    '''
    if (datetime.datetime.now(tz=pytz.utc) - self.info['bot_last_active_time']) < datetime.timedelta(minutes=5):
      return
    self.info['bot_last_active_time'] = datetime.datetime.now(tz=pytz.utc)
    self.daemon.log.info("Updating last active time.")
    updateTime = self.dbs['llBackup'].table('indices').set(value=calendar.timegm(self.info['bot_last_active_time'].utctimetuple())).where(name=self.daemon.name + '_last_active').limit(1).update()
    updateETIStatus = self.dbs['llBackup'].table('indices').set(value=int(self.daemon.eti.etiUp())).where(name='eti_up').limit(1).update()
