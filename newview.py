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
import cStringIO
import threading
import time

PORT_NUMBER = 8008
# A public geoip server. Thanks!
GEO_IP_SERVER = "http://geoip.cs.washington.edu:12679"

# This is how I though you should map urls to files when I first started with python. Hey, I coulda done worse.
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
  
  # Make what will somday be a RPC, but for now is just an HTTP request to the current node for the latency from the node to the site requested.
  def setLatValue(self, ip, url, numTests, list):
    print "Setting Latency!"
    proxy = "http://%s:%s/latency" % (ip, 63138)
    data = 'page=%s&numTests=%s' % (url[0], numTests[0])
    print "%s : %s" % (proxy, data)
    load = urllib2.urlopen(proxy, data)
    text = load.read()
    print text
    list[ip] = text
    
	# For each node, get it to do a basic latency test, and store it in a dictionary keyed by the node's ip address
  def latencyTest(self, params):
    latencyDict = {}
    for key in self.server.locations.keys():
      run = threading.Thread(target=self.setLatValue, args=[key, params['url'], params['numTests'], latencyDict])
      run.start()
    print latencyDict
    return "%s" % latencyDict
      
      
  # Load the page, either from both viewpoints server location and the requested node, or just from the node if they haven't requested a diff
  def loadPage(self, params):
    try:
      c = self.server.conn.cursor()
      c.execute('select agentstring from useragents where rowId=%s' % params['browser'][0])
      agent = c.fetchone()[0]
      self.server.curPage = params['url']
      print params['url']
      url = "http://%s:%s/page" % (params['loc'][0], 63138)
      data = 'page=%s&useragent=%s' % (params['url'][0], agent)
      print "%s : %s" % (url, data)
      proxyPage = urllib2.urlopen(url, data)
      print params['diff']
      if params['diff'][0] == '1':
        print "Diff"
        self.server.proxyCache = proxyPage.read() # Store the html from the proxy loaded page
        request = urllib2.Request(params['url'][0], headers={"User-Agent": agent})
        localPage = urllib2.urlopen(request) 
        self.server.localCache = localPage.read() # Store the html from the locally loaded page
        diffpage = open('pages/diff.html', 'r')
        #print diffpage
        return diffpage
      else:
        print "No Diff"
        return proxyPage # If we're not diffing the html between the local and remote versions, just load the remote version!
    except Exception, error: 
      print "Error: %s" % error.reason
      print self.server.vessels # Sometimes overlord dumps vessels, even after we waited before assigning them to our application. 
      print self.server.overlord.get_vessels()  # If this is the case, we may have tried to deploy to a node that we don't actually have. This lets us check.
      return error
  
  # What page have we asked for?
  def do_GET(self):
    parse = urlparse.urlparse(self.path)
    page = parse.path
    print "GET: %s" % page
    if page == "/location":
      f = self.loadPage(urlparse.parse_qs(parse.query)).read()
    elif page == "/latency":
      f = self.latencyTest(urlparse.parse_qs(parse.query))
    elif page == "/proxyCache": # The page diff page loads each page (remote or otherwise) in an iframe. This is where the proxy page is stored, and the iframe just points here
      f = self.server.proxyCache
    elif page == "/localCache": # The same as earlier, just for the local version of the page
      f = self.server.localCache
    elif page in html.keys():	# If we've recieved a request for a static page, serve it up!
      f = open(html[page], 'r').read()
    elif os.path.exists(page[1:]): # If we've got a request for a file that exists on the server, serve it up! In case you can't tell, this is at the moment utterly unrestricted and generally a bad idea. :)
      f = open(page[1:], 'r').read()
    else:
      f = open("pages/404.html", 'r').read()
    self.wfile.write(f)

  def do_POST(self):
    
    parse = urlparse.urlparse(self.path)
    page = parse.path
    print "POST: %s" % page
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
    
    #TODO: Make this suck less (It's returning hand-made JSON. Bleh)
    if page == "/locations":	# Serve up the list of locations at which we have seattle servers
      locationList = '{ "options" : ['
      for key in self.server.locations.keys():
        locationList += '{"ip" : "%s", "loc": "%s"},' % (key, self.server.locations[key][1])
      locationList = locationList[0:-1] + ']}'
      self.wfile.write(locationList)
      print locationList 
    elif page == "/browsers":  # Get the list of browsers available for the os the user has selected (for the user agent)
      c = self.server.conn.cursor()
      browserList = '{ "options" : ['
      for row in c.execute('select rowId, description from useragents where os=%s' % postvars['id'][0]):
        browserList += '{"id" : "%s", "desc" : "%s"},' % (row[0], row[1])
      browserList = browserList[0:-1] + ']}'
      self.wfile.write(browserList)
    elif page == "/platforms": # Get the list of operating systems that the user can emulate with our various saved user agent strings
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
	# Get the user, so we can find the ssh keys. Also check if the app is run in debug mode so we can print everything!
	user = sys.argv[1]
  debug = False
  if len(sys.argv) == 3:
    user = sys.argv[2] + user 
  if len(sys.argv) == 4:
    debug = True
  
  # Load the ssh keys
  if not os.path.exists('%s.publickey' % user) or not os.path.exists('%s.privatekey' % user):
    print "Error: Key files not found. Please place public and private keys" + \
      " in current working directory or at the location specified."
    sys.exit("Exit: Missing core ViewPoints Resources")
    
  # Tell overlord (the slightly modified version) to distribute 10 instances of the newproxy(pre-processed) to various seattle nodes
  init_dict = overlord.init(user, 10, 'wan', 'newproxypp.repy')
  config = overlord.get_config()
  run = threading.Thread(target=overlord.run, args=[init_dict['geni_port']])
  run.start()
  
  # Wait a bit, overlord needs its time if you don't want it to throw up everywhere
  time.sleep(60)

	# Get the geoipserver so that we can map the ips of our nodes to actual locations
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
  
  # Connect to our local database, which contains the user agent strings and their associated OSs.
  try:
    conn = sqlite3.connect('viewpoints.db')
  except:
    print("Error: Database connection failure. Cannot launch viewpoints")
    sys.exit("Exit: Missing core ViewPoints Resources") 
    
  # Start up the server! When ^c is pressed, it will still take up to a few minutes for overlord to catch up and shut down.
  try:
    server = BaseHTTPServer.HTTPServer(('', PORT_NUMBER), ViewpointsHandler)
    server.locations = locations
    server.config = config
    server.overlord = overlord
    server.vessels = overlord.get_vessels()
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
