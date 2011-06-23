"""ViewPoints.py - An application designed to evaluate website content and
performance from a variety of geolocated perspectives.

ViewPoints runs a local server to provide a user-friendly interface which then
connects to a selection of nodes from which various tests and proxy requests
can be performed.

"""
import os
import sys
import urlparse
import BaseHTTPServer
import xmlrpclib
import urllib2
import overlord
import experimentlib
import sqlite3
import cgi
import threading
import time

PORT_NUMBER = 8008
GEO_IP_SERVER = "http://geoip.cs.washington.edu:12679"

html = {'/' : "pages/index.html", '/location' : "pages/location.html", \
  '/overview' : "pages/overview.html"}
  
posts = ["/geni/renew_resources", "/viewpoints/proxy/single/getpage", \
  "/viewpoints/proxy/bulk/gettimes"]

nodes = []
vessels = []
locations = []
geoipserver = None

class ViewpointsHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  
  def addrToName(addr):
    return geoipserver.record_by_addr(addr)
      
  def loadPage(self, params):
    try:
      c = self.server.conn.cursor()
      c.execute('select agentstring from useragents where rowId=%s' % params['browser'][0])
      agent = c.fetchone()[0]
      self.server.curPage = params['url']
      return urllib2.urlopen("http://%s:%s/page" % (params['loc'][0], 63138), 'page=%s&useragent=%s' % (params['url'][0], agent))
    except urllib2.HTTPError, error:
      print "Error: %s" % error.read()
      return error
  
  def do_GET(self):
    parse = urlparse.urlparse(self.path)
    page = parse.path
    if page == "/location":
      f = self.loadPage(urlparse.parse_qs(parse.query))
    elif page in html.keys():
      f = open(html[page], 'r')
    elif os.path.exists(page[1:]):
      f = open(page[1:], 'r')
    else:
      f = open("pages/404.html", 'r')
    self.wfile.write(f.read())
    f.close()

  def do_POST(self):
    parse = urlparse.urlparse(self.path)
    page = parse.path
    
    #Get any posted variables, consider other content types.
    if  self.headers.getheader('content-type'):
      ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
      if ctype == 'multipart/form-data':
          postvars = cgi.parse_multipart(self.rfile, pdict)
      elif ctype == 'application/x-www-form-urlencoded':
          length = int(self.headers.getheader('content-length'))
          postvars = cgi.parse_qs(self.rfile.read(length), keep_blank_values=1)
      else: 
        postvars= {}
    
    #TODO: Neaten/create function for JSON construction. 
    if page == "/locations":
      locationList = '{ "options" : ['
      for key in self.server.locations.keys():
        locationList += '{"ip" : "%s", "loc": "%s"},' % (key, self.server.locations[key][1])
      locationList = locationList[0:-1] + ']}'
      self.wfile.write(locationList)
      print locationList 
    elif page == "/browsers":
      c = self.server.conn.cursor()
      browserList = '{ "options" : ['
      for row in c.execute('select rowId, description from useragents where os=%s' % postvars['id'][0]):
        browserList += '{"id" : "%s", "desc" : "%s"},' % (row[0], row[1])
      browserList = browserList[0:-1] + ']}'
      self.wfile.write(browserList)
    elif page == "/platforms":
      print "Platforms"
      c = self.server.conn.cursor()
      print c
      platList = '{ "options" : ['
      for row in c.execute('select rowId, name from os'):
        print row
        platList += '{"id" : "%s", "desc" : "%s"},' % (row[0], row[1])
      platList = platList[0:-1] + ']}'
      print platList
      self.wfile.write(platList)
      


def main():
  user = sys.argv[1]
  debug = False
  if len(sys.argv) == 3:
    user = sys.argv[2] + user 
  if len(sys.argv) == 4:
    debug = True
  
  if not os.path.exists('%s.publickey' % user) or not os.path.exists('%s.privatekey' % user):
    print "Error: Key files not found. Please place public and private keys" + \
      " in current working directory or at the location specified."
    sys.exit("Exit: Missing core ViewPoints Resources")
    
  init_dict = overlord.init(user, 10, 'wan', 'newproxypp.repy')
  config = overlord.get_config()
  run = threading.Thread(target=overlord.run, args=[init_dict['geni_port']])
  run.start()
  
  time.sleep(60)

  locations = {}  
  geoipserver = xmlrpclib.ServerProxy(GEO_IP_SERVER)

  for vessel in overlord.get_vessels():
    nodeid, vesselname = vessel.split(":")
    location = experimentlib.get_node_location(nodeid).split(":")[0]
    locations[location] = [vessel]
    if debug:
      try:
        log = experimentlib.get_vessel_log(vessel, config['identity'])
        print "Log for %s: %s" (location, log) 
      except:
        print "Unnexpected Error: %s" % sys.exc_info()[0]
    try:
      loc = geoipserver.record_by_addr(location)
      locations[location].append("%s - %s" % (loc['city'], loc['country_name'])) 
    except:
      locations[location].append("%s (No Location Data)" % location)
  conn = None  
  
  try:
    conn = sqlite3.connect('viewpoints.db')
  except:
    print("Error: Database connection failure. Cannot launch viewpoints")
    sys.exit("Exit: Missing core ViewPoints Resources") 
    
  try:
    server = BaseHTTPServer.HTTPServer(('', PORT_NUMBER), ViewpointsHandler)
    server.locations = locations
    server.config = config
    server.conn = conn
    print 'Starting local ViewPoints server...'
    server.serve_forever()
    print 'Server running on port %d' % PORT_NUMBER
  except KeyboardInterrupt:
    print 'Break request recieved. Shutting down server.'
    overlord.KEEP_RUNNING = False
    server.conn.close()
    server.socket.close()


if __name__ == "__main__":
  main()
