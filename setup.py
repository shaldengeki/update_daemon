try:
  from setuptools import setup
except ImportError:
  from distutils.core import setup

config = {
  'description': 'update_daemon', 
  'author': 'Shal Dengeki', 
  'url': 'https://github.com/shaldengeki/update_daemon', 
  'download_url': 'https://github.com/shaldengeki/update_daemon', 
  'author_email': 'shaldengeki@gmail.com', 
  'version': '0.1', 
  'install_requires': ['nose', 'albatross', 'DbConn', 'MailServer', 'configobj', 'pytz'], 
  'packages': ['update_daemon'], 
  'scripts': [],
  'name': 'update_daemon'
}

setup(**config)