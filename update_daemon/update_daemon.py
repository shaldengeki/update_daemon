# !/usr/bin/env python

''' 
  update_daemon - Provides base update daemon functionality.
  Author - Shal Dengeki <shaldengeki@gmail.com>
  REQUIRES - configobj, filelock, argsparse
'''

import configobj
import httplib

import sys
import time
import traceback

from pubsub import pub

import filelock
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

class Daemon(object):
  """
    Generic update daemon class.
  """

  def __init__(self, name, listeners, config_file=None):
    """
      Initializes update daemon.
      Takes a list of listeners in listeners.
      Takes string file path for config_file.
    """
    self.name = name
    self.listeners = listeners
    self.config_file = unicode(config_file)
    self.load_config()
    self.info = {}

  def load_config(self, config_file=None):
    if config_file is not None:
      self.config_file = unicode(config_file)

    self.config = configobj.ConfigObj(self.config_file)

  def preload(self):
    """
      Tasks to be run after initialization, but before updating.
      Fetch additional daemon-specific config / timing info and store it in self.info here.
    """
    pass

  def subscribe_all(self):
    """
      Subscribes all listeners to pubsub under their desired topics.
    """
    for listener,topics in self.listeners:
      if isinstance(topics, list):
        for topic in topics:
          pub.subscribe(listener, topic)
      else:
        pub.subscribe(listener, topics)

  def on_fail(self, e, trace):
    """
      Executed upon failure of inner daemon loop.
      Do some logging or send an email here.
      Return a bool reflecting whether or not to continue running.
    """
    return False

  def clean_up(self):
    """
      Run once on_fail() is called and returns false.
    """
    pass

  def run(self):
    """
      Runs the update daemon indefinitely.
    """
    while True:
      try:
        self.preload()
        while True:

      except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        if not self.on_fail(e, traceback.extract_tb(exc_traceback)):
          self.clean_up()
          break
        time.sleep(int(self.config['loop_interval']))