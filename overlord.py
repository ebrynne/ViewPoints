"""
<Program Name>
  Overlord Deployment and Monitoring Library

<Author>
  Evan Meagher

<Date Started>
  May 1, 2010

<Description>
  A library for deploying an arbitrary repy program on a number of vessels.
  Built on top of the Experiment Library, Overlord persistently manages a
  user-defined number of vessels, ensuring that the specified service is up
  and running.

<Requirements>
  Overlord must be in the same directory as a GENI user's public and
  private keys. Also, an instance of the Experiment Library must also be in a
  subdirectory named 'experimentlibrary'. This directory can be setup by
  following the instructions on the Seattle wiki:
  https://seattle.cs.washington.edu/wiki/ExperimentLibrary

  Also note that Overlord requires a secure connection to SeattleGENI.
  To perform secure SSL communication with SeattleGENI, you must:
    * Have M2Crypto installed (http://chandlerproject.org/Projects/MeTooCrypto)
    * Have a PEM file, cacert.pem, containing CA certificates in the
      experimentlibrary directory. One such file can be found at
      http://curl.haxx.se/ca/cacert.pem

  For more inforation on SSL communication with SeattleGENI, see
  https://seattle.cs.washington.edu/wiki/SeattleGeniClientLib
  
<Usage>
  To create an Overlord client, simply import it:

    import overlord

  and then call the init() and run() functions with your desired parameters.
  For example, to deploy time servers on 10 wan vessels:

    import overlord
    init_dict = overlord.init(GENI_USERNAME, 10, 'wan', 'time_server.py')
    overlord.run(init_dict['geni_port'])

  Note that time_server.py requires a port number as an argument, so the user's
  GENI port is passed to the run() function.
    
  For more examples of using this experimentlib, see the examples/ directory.

  Please also see the following wiki page for usage information and how to
  obtain the latest version of this library:
  https://seattle.cs.washington.edu/wiki/Overlord

"""

import os
import sys
import time
sys.path.append("experimentlibrary")
import experimentlib as explib


# Increase the timeout used by the experiment library, so uploads of program
# file won't time out
explib.defaulttimeout = 90

# How often vessel status should be polled, in seconds
VESSEL_POLLING_TIME = 30

# Log a liveness message after this many iterations of the main loop
LOG_AFTER_THIS_MANY_LOOPS = 96

# How often to renew vessels, in seconds
VESSEL_RENEWAL_PERIOD = 518400

KEEP_RUNNING = True

# Dictionary of configuration info
config = {
  'identity': None,
  'geni_port': '',
  'logfilename': sys.argv[0][:-3] + '.log',
  'logfile': '',
  'vesselcount': 0,
  'vesseltype': '',
  'program_filename': ''
  }


  
def init(geni_username, vesselcount, vesseltype, program_filename):
  """
  <Purpose>
    Initializes the deployment of an arbitrary service. Populates a global
    configuration dictionary and returns a dict of data that could be required
    by the run() function. init() must be called before the run() function.

    Note on the return dict:
      The return value of init() is meant to contain data that is needed by
      calls to explib.start_vessel() within the run() function. At the time of
      creation of this library, the only such data that is required by
      deployable services is the user's GENI port.

      To add support for services requiring more arguments, simply add the
      necessary data to the dictionary returned by this function.

  <Arguments>
    geni_username
      SeattleGENI username. Used to locate and handle public and private key
      files.
    vesselcount
      The number of vessels on which to deploy.
    vesseltype
      The type of vessel to acquire, based on the SEATTLEGENI_VESSEL_TYPE_*
      constants within experimentlib.py
    program_filename
      The filename of the program to deploy and monitor on vessels.

  <Exceptions>
    ValueError
      Raised if argument vesseltype doesn't match one of the experimentlib
      SEATTLEGENI_VESSEL_TYPE_* constants, if argument program file does not
      exist, or if argument number of vessels on which to deploy exceeds the
      user's number of vessel credits.

  <Side Effects>
    Initializes certain global variables.
    
  <Returns>
    A dictionary containing data that clients might need for running program on
    vessels.
  """
  
  # Fill config dict with argument data
  # Validate vesseltype, based on constants in explib
  if vesseltype not in [explib.SEATTLEGENI_VESSEL_TYPE_WAN,
                        explib.SEATTLEGENI_VESSEL_TYPE_LAN,
                        explib.SEATTLEGENI_VESSEL_TYPE_NAT,
                        explib.SEATTLEGENI_VESSEL_TYPE_RAND]:
    raise ValueError('Invalid vessel type specified. Argument vessel type must be one of the SEATTLEGENI_VESSEL_TYPE_* constants defined in experimentlib.py')
  config['vesseltype'] = vesseltype
    
  # Verify that program file exists
  if not os.path.isfile(program_filename):
    raise ValueError('Specified program file ' + program_filename + ' does not exist')
  config['program_filename'] = program_filename
    
  # Setup explib identity object and GENI details
  config['identity'] = explib.create_identity_from_key_files(
    geni_username + '.publickey',
    geni_username + '.privatekey')
  config['geni_port'] = explib.seattlegeni_user_port(config['identity'])

  # Validate number of vessels on which to deploy
  num_vslcredits = explib.seattlegeni_max_vessels_allowed(config['identity'])
  if vesselcount > num_vslcredits:
    raise ValueError('Invalid number of vessels specified. The number of deployed vessels must be less than or equal to the user\'s number of vessel credits.')
  config['vesselcount'] = vesselcount


  # Create and populate the return dict
  ret_dict = {
    'geni_port': config['geni_port']
    }

  return ret_dict

  



def acquire_vessels(number):
  """
  <Purpose>
    Acquire an argument number of vessels via SeattleGENI. Vessel type is
    obtained from the config dictionary. This function is a wrapper around the
    Experiment Library function seattlegeni_acquire_vessels, with logging
    support.

  <Arguments>
    number
      The number of vessels to acquire.

  <Exceptions>
    None

  <Side Effects>
    None
    
  <Returns>
    A list of vesselhandles of freshly-acquired vessels. On failure, returns an
    empty list.
  """

  # Log the fact that vessels are being acquired
  config['logfile'].write(str(time.time()) + ': Acquiring ' + str(number) + ' vessel(s)...')
  config['logfile'].flush()

  # Attempt to acquire vessels. Log success or failure, accordingly.
  try:
    vesselhandle_list = explib.seattlegeni_acquire_vessels(config['identity'],
                                                           config['vesseltype'],
                                                           number)
  except explib.SeattleGENIError, e:
    config['logfile'].write('failure\n')
    config['logfile'].write('Error was: ' + str(e) + '\n')
    return []
  else:
    config['logfile'].write('success\n')
  finally:
    config['logfile'].flush()

  # Renew vessels to maximum expiration time
  explib.seattlegeni_renew_vessels(config['identity'], vesselhandle_list)
  
  return vesselhandle_list





def upload_to_vessels(vesselhandle_list, filename):
  """
  <Purpose>
    Uploads a file to a set of vessels. A batch wrapper around the Experiment
    Library function upload_file_to_vessel, with logging support.

  <Arguments>
    vesselhandle_list
      A list of vesselhandles of vessels to which the file is to be uploaded.
    filename
      The filename of the file to be uploaded.

  <Exceptions>
    None

  <Side Effects>
    None
    
  <Returns>
    A list of vessels to which the upload succeeded.
  """

  # Log the fact that uploads are occurring
  config['logfile'].write(str(time.time()) + ': Uploading ' + filename + ' to '+ str(len(vesselhandle_list)) + ' vessel(s)...\n')
  config['logfile'].flush()


  # Initially set return list equal to argument vesselhandle list
  success_list = vesselhandle_list
  failed_list = []
  # For each vesselhandle, attempt an upload
  for vh in vesselhandle_list:
    try:
      explib.upload_file_to_vessel(vh, config['identity'], filename)
    except explib.NodeCommunicationError, e:
      # If upload failed, remove from vesselhandle_list...
      success_list.remove(vh)
      # ...add to failed_list...
      failed_list.append(vh)
      # ...and lookup the nodelocation so it can be logged
      nodeid, vesselname = explib.get_nodeid_and_vesselname(vh)
      nodelocation = explib.get_node_location(nodeid)
      config['logfile'].write('Failure on vessel ' + nodelocation + '\n')
      config['logfile'].write('Error was: ' + str(e) + '\n')
      config['logfile'].flush()
      
  release_vessels(failed_list, 'Releasing ' + str(len(failed_list)) + ' vessels to which upload failed...')
  return success_list





def run_on_vessels(vesselhandle_list, filename, *args):
  """
  <Purpose>
    Runs a program on a set of vessels. A batch wrapper around the Experiment
    Library function run_parallelized, with logging support.

  <Arguments>
    vesselhandle_list
      A list of vesselhandles of vessels to which a file is to be uploaded.
    filename
      The filename of the program to run.
    *args
      Optional additional arguments required by the program to be run on
      vessels.

  <Exceptions>
    None

  <Side Effects>
    None
    
  <Returns>
    A tuple of:
      (successlist, failurelist)
    where successlist and failedlist are lists of vesselhandles of vessels on
    which the program succeeded and failed to run, respectively.

  """

  # Log the fact that program execution is occurring
  config['logfile'].write(str(time.time()) + ': Starting program on ' + str(len(vesselhandle_list)) + ' vessel(s)...\n')
  config['logfile'].flush()

  # Initialize empty return lists
  success_list = []
  failed_list = []

  # Attempt to run program on each vessel
  for vh in vesselhandle_list:
    try:
      # Note: list comp used to turn *args tuple into list of strings
      explib.start_vessel(vh, config['identity'], filename, [str(i) for i in list(args)])
    except explib.SeattleExperimentError, e:
      # If failure detected, add vessel to failed_list
      failed_list.append(vh)
    else:
      # If execution successful, add vessel to success_list
      success_list.append(vh)

  return success_list, failed_list





def release_vessels(vesselhandle_list, log_string):
  """
  <Purpose>
    Releases a set of vessels. A batch wrapper around the Experiment Library
    function run_parallelized, with logging support. Logs log_string as the
    reason for releasing vessels.

    Note on format of log_string:
      Depending on the outcome of the attempted release operation, this
      function appends 'success' or 'failure' to its associated log entry.
      Thus, callers are advised to end the log_string argument in an ellipsis
      (...) to adhere to the logging conventions of this script.
      
      Example: logstring => 'Releasing a few vessels...'

  <Arguments>
    vesselhandle_list
      A list of vesselhandles of vessels to release.
    log_string
      A string describing the reason for vessel release.

  <Exceptions>
    None

  <Side Effects>
    None
    
  <Returns>
    None
  """

  # If vesselhandle_list is empty, do nothing
  if vesselhandle_list:
    # Log the fact that vessel release is occurring
    config['logfile'].write(str(time.time()) + ': ' + log_string)
    config['logfile'].flush()
    try:
      explib.seattlegeni_release_vessels(config['identity'], vesselhandle_list)
    except explib.SeattleGENIError, e:
      config['logfile'].write('failure\n')
      config['logfile'].write('Error was: ' + str(e) + '\n')
    else:
      config['logfile'].write('success\n')
    finally:
      config['logfile'].flush()





def list_difference(list1, list2):
  """
  Returns the difference (set operation) of list1 - list2.
  """
  return list(set(list1).difference(set(list2)))

def get_vessels():
  print "Config: %s" % config
  return explib.seattlegeni_get_acquired_vessels(config['identity'])

def get_config():
  return config

def run(*args):
  """
  <Purpose>
    Starts the deployment and monitoring of a service on a number of vessels.
    Handles all acquisition of, uploading to, starting, and release of vessels.
    Contains the main loop of this program, and is thus the final function to
    call in all client programs. Requires init() to have been called prior to
    running.
  
  <Arguments>
    *args

  <Exceptions>
    None

  <Side Effects>
    Persistently writes to a log file.
    
  <Returns>
    None
  """
  # Write logfile header
  config['logfile'] = open(config['logfilename'], 'w')
  config['logfile'].write('################################################\n')
  config['logfile'].write('##   Overlord Deployment and Monitoring Log   ##\n')
  config['logfile'].write('################################################\n\n')
  config['logfile'].write('GENI user:              ' + config['identity']['username'] + '\n')
  config['logfile'].write('Vessels to monitor:     ' + str(config['vesselcount']) + '\n')
  config['logfile'].write('Time of script start:   ' + str(time.time()) + '\n\n')
  config['logfile'].flush()

  
  # Release any preallocated vessels
  vesselhandle_list = explib.seattlegeni_get_acquired_vessels(config['identity'])
  release_vessels(vesselhandle_list, 'Releasing ' + str(len(vesselhandle_list)) + ' preallocated vessels...')

  
  # Acquire an initial sample of vessels
  config['logfile'].write(str(time.time()) + ': Fetching initial batch of ' + str(config['vesselcount']) + ' vessels:\n')
  config['logfile'].flush()
  vesselhandle_list = []
  while not vesselhandle_list:
    vesselhandle_list = acquire_vessels(config['vesselcount'])

  # Upload program to vessels
  vesselhandle_list = upload_to_vessels(vesselhandle_list, config['program_filename'])


  # Run program on vessels
  vesselhandle_list, failed_list = run_on_vessels(vesselhandle_list,
                                             config['program_filename'],
                                             *args)


  # Release any failed vessels
  if failed_list:
    config['logfile'].write(str(time.time()) + ': Running ' + config['program_filename'] + ' failed on ' + str(len(failed_list)) + ' vessels\n')

    # Get details about failed vessel(s) and log them
    for vh in failed_list:
      try:
        vessel_log = explib.get_vessel_log(vh, config['identity'])
      except:
        vessel_log = '[ERROR: vessel log fetch failed]'
        
      nodeid, vesselname = explib.get_nodeid_and_vesselname(vh)
      nodelocation = explib.get_node_location(nodeid)
      
      # Log the vessel's log contents
      config['logfile'].write('Log contents of failed vessel at ' + nodelocation + ': ' + vessel_log + '\n')
      config['logfile'].flush()
      
    # Release the failed vessels
    release_vessels(failed_list, 'Releasing failed vessel(s)...')



  # Initialize counter variable for loop iterations
  loop_iterations = 0
  PREPPED = True
  print "PREPPED!"
  print "Vessel Handles: %s" % vesselhandle_list

  # Main loop
  while KEEP_RUNNING == True:
    print "Starting Loop!"
    # Check for vessels not in started state
    stopped_vessel_list = []
    for vh in vesselhandle_list:
      try:
        vessel_status = explib.get_vessel_status(vh, config['identity'])
        log = explib.get_vessel_log(vh, config['identity'])
        print "Loop Log: %s" % log
      except:
        # Node lookup failed, so remove vessel from vesselhandle_list
        # TODO: proper way to handle failed advertisements?
        stopped_vessel_list.append(vh)
      else:
        if vessel_status != explib.VESSEL_STATUS_STARTED:
          stopped_vessel_list.append(vh)

    # Release and replace any stopped vessels
    if stopped_vessel_list:
      # Release any stopped vessels
      release_vessels(stopped_vessel_list, 'Releasing ' + str(len(stopped_vessel_list)) + ' stopped vessel(s)...')

      # Remove released vessels from vesselhandle_list
      vesselhandle_list = list_difference(vesselhandle_list, stopped_vessel_list)

    # Ensure that enough vessels are running
    if len(vesselhandle_list) < config['vesselcount']:
      # If there aren't enough active vessels, acquire some
      config['logfile'].write(str(time.time()) + ': Only ' + str(len(vesselhandle_list)) + ' vessel(s) out of target ' + str(config['vesselcount']) + ' detected\n')
      config['logfile'].flush()
      fresh_vessels = acquire_vessels(config['vesselcount'] - len(vesselhandle_list))

      # Upload and run program to/on fresh vessels
      fresh_vessels = upload_to_vessels(fresh_vessels, config['program_filename'])
      success_list, failed_list = run_on_vessels(fresh_vessels,
                                                 config['program_filename'],
                                                 *args)

      # Release any failed vessels
      if failed_list:
        config['logfile'].write(str(time.time()) + ': Running ' + config['program_filename'] + ' failed on ' + str(len(failed_list)) + ' vessels\n')

        # Get details about failed vessel(s) and log them
        for vh in failed_list:
          try:
            vessel_log = explib.get_vessel_log(vh, config['identity'])
          except:
            vessel_log = '[ERROR: vessel log fetch failed]'

          nodeid, vesselname = explib.get_nodeid_and_vesselname(vh)
          nodelocation = explib.get_node_location(nodeid)

          # Log the vessel's log contents
          config['logfile'].write('Log contents of failed vessel at ' + nodelocation + ': ' + vessel_log + '\n')
          config['logfile'].flush()

        # Release the failed vessels
        release_vessels(failed_list, 'Releasing failed vessel(s)...')
        
        # Remove released vessels from fresh_vessels list
        fresh_vessels = list_difference(fresh_vessels, failed_list)

      # Add fresh_vessels to vesselhandle_list
      vesselhandle_list.extend(fresh_vessels)


    # Sleep for parameterized amount of time
    time.sleep(VESSEL_POLLING_TIME)
    
    # Log a liveness message every certain number of iterations
    loop_iterations += 1
    if loop_iterations % LOG_AFTER_THIS_MANY_LOOPS == 0:
      config['logfile'].write(str(time.time()) + ': Still alive...\n')
      config['logfile'].flush()

    # Renew vessels according to constant period
    if loop_iterations * VESSEL_POLLING_TIME > VESSEL_RENEWAL_PERIOD:
      explib.seattlegeni_renew_vessels(config['identity'], vesselhandle_list)
      loop_iterations = 0
