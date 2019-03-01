# Fuzzer system to run tests

#!/usr/bin/env python
import os
import re
import sys
import stat
import subprocess
import argparse
import time
from ace import random_engine


class Log(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush() 
    def flush(self) :
        for f in self.files:
            f.flush()

def build_parser():
    parser = argparse.ArgumentParser(description='XFSMonkey')

    # global args
    parser.add_argument('--fs_type', '-t', default='ext4', help='Filesystem on which you wish to run tests using XFSMonkey. Default = ext4')

    # crash monkey args
    parser.add_argument('--disk_size', '-e', default=102400, type=int, help='Size of disk in KB. Default = 200MB')
    parser.add_argument('--iterations', '-s', default=10000, type=int, help='Number of random crash states to test on. Default = 1000')
    parser.add_argument('--test_dev', '-d', default='/dev/cow_ram0', help='Test device. Default = /dev/cow_ram0')
    parser.add_argument('--flag_dev', '-f', default='/dev/sda', help='Flag device. Default = /dev/sda')
    
    #Requires changes to Makefile to place our xfstests into this folder by default.
    parser.add_argument('--time', '-T', default='60', help='Time to run the fuzzer. Default = 60 seconds')
    parser.add_argument('--length', '-l', default='10', help='Max length of workload. Default = 10')
    return parser

def cleanup():
	#clean up umount and rmmod errors
	command = 'umount /mnt/snapshot; rmmod ./build/disk_wrapper.ko; rmmod ./build/cow_brd.ko'
	p=subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
	(out, err) = p.communicate()
	p.wait()
	#print 'Done cleaning up test harness'

def get_current_epoch_micros():
    return int(time.time() * 1000)


def get_time_string():
    epoch_micros = get_current_epoch_micros()
    epoch_secs = epoch_micros / 1000
    micros = epoch_micros % 1000

    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(epoch_secs)) + '.' + str(micros) + ' '
    # return time.strftime('%c') + ' '


def get_time_from_epoch(epoch_secs):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(epoch_secs))

def print_setup(parsed_args):
	#print(get_time_string() + 'Starting xfsMonkey run..')
	#print '\n{: ^50s}'.format('XFSMonkey\n')
	print '='*20, 'Setup' , '='*20, '\n'
	print '{0:20}  {1}'.format('Filesystem type', parsed_args.fs_type)
	print '{0:20}  {1}'.format('Disk size (MB)', parsed_args.disk_size/1024)
	#print '{0:20}  {1}'.format('Iterations per test', parsed_args.iterations)
	print '{0:20}  {1}'.format('Test device', parsed_args.test_dev)	
	print '{0:20}  {1}'.format('Flags device', parsed_args.flag_dev)	
	print '{0:20}  {1}'.format('Test path', 'build/fuzzer')	
	print '\n', '='*48, '\n'

def main():

	# Open the log file
	log_file = time.strftime('%Y%m%d_%H%M%S') + '-fuzzer.log'
	log_file_handle = open(log_file, 'w')
	original = sys.stdout
	sys.stdout = Log(sys.stdout, log_file_handle)

	parsed_args = build_parser().parse_args()
 
	os.chdir('ace')
	random_engine.setup()
 	os.chdir('..')
	#Print the test setup
	print_setup(parsed_args)

	#Assign a test num
	test_num = 0
	
	#This is the directory that contains the bug reports from this xfsMonkey run
	subprocess.call('mkdir diff_results', shell=True)
	subprocess.call('echo 0 > missing; echo 0 > stat; echo 0 > bugs; echo 0 > others', shell=True)    

	#Get the relative path to test directory
	xfsMonkeyTestPath = './build/fuzzer'
	start_time =time.time()
	runtime = float(parsed_args.time)
	upper_bound = int(parsed_args.length)
	while (time.time() - start_time) < runtime:
			os.chdir('ace')
			filename = random_engine.produceWorkload(upper_bound, False, True) + '.so'
			os.chdir('..')
			subprocess.call('make fuzzer -B', shell=True)
      
			#Assign a snapshot file name for replay using CrashMonkey.
			#If we have a large number of tests in the test suite, then this might blow 
			#up space. (Feature not implemented yet).
			snapshot = filename.replace('.so', '') + '_' + parsed_args.fs_type

			#Get full test file path
			test_file = xfsMonkeyTestPath.replace('./build/', '') + filename

			#Build command to run c_harness 
			command = ('cd build; ./c_harness -v -c -P -f '+ parsed_args.flag_dev +' -d '+
			parsed_args.test_dev +' -t ' + parsed_args.fs_type + ' -e ' + 
			str(parsed_args.disk_size) + ' ' + test_file + ' 2>&1')
	
			#Cleanup errors due to prev runs if any
			cleanup()


			#Print the test number
			test_num+=1
			log = '\n' + '-'*20 + 'Test #' + `test_num` +  '-'*20 + '\n'
			log_file_handle.write(log)

			#Run the test now
			log =  get_time_string() + 'Running test : '+ filename.replace('.so', '') + 'as Crashmonkey standalone \n'
			log_file_handle.write(log)
			sys.stdout.write('Running test #' + str(test_num) + ' : ' + filename.replace('.so', '')) 
			#get_time_string(), 'Running...'
			
			#Sometimes we face an error connecting to socket. So let's retry one more time
			#if CM throws a error for a particular test.
			retry = 0
			while True:
				p=subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
				(output,err)=p.communicate()
				p_status=p.wait()

				# Printing the output on stdout seems too noisy. It's cleaner to have only the result
				# of each test printed. However due to the long writeback delay, it seems as though
				# the test case hung. 
				# (TODO : Add a flag in c_harness to interactively print when we wait for writeback
				# or start testing)
				res = re.sub(r'(?s).*Reordering', '\nReordering', output, flags=re.I)
				res_final = re.sub(r'==.*(?s)', '\n', res)

				#print output
				retry += 1
				if (p_status == 0 or retry == 4):
					if retry == 4 and p_status != 0 :
						log_file_handle.write(get_time_string() + 'Could not run test : ' + filename.replace('.so', ''))
					else:
						log_file_handle.write(res_final)	
					break
				else:
					error = re.sub(r'(?s).*error', '\nError', output, flags=re.I)
					log_file_handle.write(get_time_string() +  error)
					#os.system('bash vm_scripts/cm_cleanup.sh')
					cleanup()
					log_file_handle.write(get_time_string() + 'Retry running ' + filename.replace('.so', '') + '\n' + get_time_string() + 'Running... ')	 
			file = filename.replace('.so', '')
      			
			#diff_command = 'tail -vn +1 build/diff* >> diff_results/' + file  + '; rm build/diff*' 
			#subprocess.call('cat build/diff* > out', shell=True)
            
			#Get the last numbered diff file if present, and clean up diffs
			subprocess.call('cat build/$(ls build/ | grep diff | tail -n -1) > out 2>/dev/null', shell=True)
			diff_command = './copy_diff.sh out ' + file + ' 1'
			#subprocess.call('tail -vn +1 build/diff*', shell=True)
			subprocess.call(diff_command, shell=True)
			
	log_file_handle.write('\n'+ get_time_string() + ': Test completed. See ' + log_file + ' for test summary\n')
	#Stop logging
	sys.stdout = original
	log_file_handle.close()
	print "\nTesting complete...\n"

if __name__ == '__main__':
	main()