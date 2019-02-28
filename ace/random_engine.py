#!/usr/bin/env python

#To run : python ace_random.py -l <seq_length> -n <amount>
import os
import re
import sys
import stat
import subprocess
import argparse
import time
import itertools
import json
import pprint
import collections
import threading
import random
from progressbar import *
from shutil import copyfile
from string import maketrans
from multiprocessing import Pool
from progress.bar import *


#All functions that has options go here

FallocOptions = ['FALLOC_FL_ZERO_RANGE', 'FALLOC_FL_ZERO_RANGE|FALLOC_FL_KEEP_SIZE','FALLOC_FL_PUNCH_HOLE|FALLOC_FL_KEEP_SIZE','FALLOC_FL_KEEP_SIZE', 0]

FsyncOptions = ['fsync','fdatasync', 'sync']

#This should take care of file name/ dir name
#Default option : test, test/A [foo, bar] , test/B [foo, bar]
# We have seperated it out into two sets, first and second, in order to eliminate duplicate workloads that differ just in terms of file names.
FileOptions = ['foo', 'A/foo'] #foo
SecondFileOptions = ['bar', 'A/bar'] #bar

#A,B are  subdirectories under test
# test directory(root) is under a separate list because we don't want to try to create/remove it in the workload. But we should be able to fsync it.
DirOptions = ['A']
TestDirOptions = ['test']
SecondDirOptions = ['B']


#this will take care of offset + length combo
#Start = 4-16K , append = 16K-20K, overlap = 8000 - 12096, prepend = 0-4K

#Append should append to file size, and overwrites should be possible
#WriteOptions = ['append', 'overlap_unaligned_start', 'overlap_extend', 'overlap_unaligned_end']
WriteOptions = ['append', 'overlap_unaligned_start', 'overlap_extend'] # 'overlap_unaligned_end'


#d_overlap = 8K-12K (has to be aligned)
#dWriteOptions = ['append', 'overlap_start', 'overlap_end']
dWriteOptions = ['append', 'overlap_start'] # 'overlap_end'

#Truncate file options 'aligned'
TruncateOptions = ['unaligned']

#Set of file-system operations to be used in test generation.
# We currently support : creat, mkdir, falloc, write, dwrite, link, unlink, remove, rename, fsetxattr, removexattr, truncate, mmapwrite, symlink, fsync, fdatasync, sync
OperationSet = ['creat', 'mkdir', 'falloc', 'write', 'dwrite','mmapwrite', 'link', 'unlink', 'remove', 'rename', 'fsetxattr', 'removexattr', 'truncate', 'fdatasync']

#The sequences we want to reach to, to reproduce known bugs.
expected_sequence = []
expected_sync_sequence = []


#return sibling of a file/directory
def SiblingOf(file):
    if file == 'foo':
        return 'bar'
    elif file == 'bar' :
        return 'foo'
    elif file == 'A/foo':
        return 'A/bar'
    elif file == 'A/bar':
        return 'A/foo'
    elif file == 'B/foo':
        return 'B/bar'
    elif file == 'B/bar' :
        return 'B/foo'
    elif file == 'AC/foo':
        return 'AC/bar'
    elif file == 'AC/bar' :
        return 'AC/foo'
    elif file == 'A' :
        return 'B'
    elif file == 'B':
        return 'A'
    elif file == 'AC' :
	return 'AC'
    elif file == 'test':
        return 'test'

#Return parent of a file/directory
def Parent(file):
    if file == 'foo' or file == 'bar':
        return 'test'
    if file == 'A/foo' or file == 'A/bar' or file == 'AC':
        return 'A'
    if file == 'B/foo' or file == 'B/bar':
        return 'B'
    if file == 'A' or file == 'B' or file == 'test':
        return 'test'
    if file == 'AC/foo' or file == 'AC/bar':
        return 'AC'


# Given a list of files, return a list of related files.
# These are optimizations to reduce the effective workload set, by persisting only related files during workload generation.
def file_range(file_list):
    file_set = list(file_list)
    for i in xrange(0, len(file_list)):
        file_set.append(SiblingOf(file_list[i]))
        file_set.append(Parent(file_list[i]))
    return list(set(file_set))

def build_parser():
    parser = argparse.ArgumentParser(description='Automatic Crash Explorer - r v0.1')

    # global args
    parser.add_argument('--sequence_len', '-l', default='3', help='Number of critical ops in the bugy workload')
    parser.add_argument('--amount', '-n', default='10', help='Number of Workloads to generate?')

    return parser


def print_setup(parsed_args):
    print '\n{: ^50s}'.format('Automatic Crash Explorer v0.1\n')
    print '='*20, 'Setup' , '='*20, '\n'
    print '{0:20}  {1}'.format('Sequence length', parsed_args.sequence_len)
    print '{0:20}  {1}'.format('Amount', parsed_args.amount)
    print '\n', '='*48, '\n'


# Helper to build all possible combination of parameters to a given file-system operation
def buildTuple(command):
    if command == 'creat':
        d = tuple(FileOptions)
    elif command == 'mkdir' or command == 'rmdir':
        d = tuple(DirOptions)
    elif command == 'mknod':
        d = tuple(FileOptions)
    elif command == 'falloc':
        d_tmp = list()
        d_tmp.append(FileOptions)
        d_tmp.append(FallocOptions)
        d_tmp.append(WriteOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            d.append(i)
    elif command == 'write':
        d_tmp = list()
        d_tmp.append(FileOptions)
        d_tmp.append(WriteOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            d.append(i)
    elif command == 'dwrite':
        d_tmp = list()
        d_tmp.append(FileOptions)
        d_tmp.append(dWriteOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            d.append(i)
    elif command == 'link' or command == 'symlink':
        d_tmp = list()
        d_tmp.append(FileOptions + SecondFileOptions)
        d_tmp.append(SecondFileOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            if len(set(i)) == 2:
                d.append(i)
    elif command == 'rename':
        d_tmp = list()
        d_tmp.append(FileOptions + SecondFileOptions)
        d_tmp.append(SecondFileOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            if len(set(i)) == 2:
                d.append(i)
        d_tmp = list()
        d_tmp.append(DirOptions + SecondDirOptions)
        d_tmp.append(SecondDirOptions)
        for i in itertools.product(*d_tmp):
            if len(set(i)) == 2:
                d.append(i)
    elif command == 'remove' or command == 'unlink':
        d = tuple(FileOptions +SecondFileOptions)
    elif command == 'fdatasync' or command == 'fsetxattr' or command == 'removexattr':
        d = tuple(FileOptions)
    elif command == 'fsync':
        d = tuple(FileOptions + DirOptions + TestDirOptions +  SecondFileOptions + SecondDirOptions)
    elif command == 'truncate':
        d_tmp = list()
        d_tmp.append(FileOptions)
        d_tmp.append(TruncateOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            d.append(i)
    elif command == 'mmapwrite':
        d_tmp = list()
        d_tmp.append(FileOptions)
        d_tmp.append(dWriteOptions)
        d = list()
        for i in itertools.product(*d_tmp):
            d.append(i)
    else:
        d=()
    return d




# Find the auto-generated workload that matches the necoded sequence of known bugs. This is to sanity check that Ace can indeed generate workloads to reproduce the bug, if run on appropriate kernel veersions.
def isBugWorkload(opList, paramList, syncList):
    for i in xrange(0,len(expected_sequence)):
        if len(opList) != len(expected_sequence[i]):
            continue
        
        flag = 1
        
        for j in xrange(0, len(expected_sequence[i])):
            if opList[j] == expected_sequence[i][j][0] and paramList[j] == expected_sequence[i][j][1] and tuple(syncList[j]) == tuple(expected_sync_sequence[i][j]):
                continue
            else:
                flag = 0
                break
    
        if flag == 1:
            print 'Found match to Bug # ', i+1, ' : in file # ' , global_count
            print 'Length of seq : ',  len(expected_sequence[i])
            print 'Expected sequence = ' , expected_sequence[i]
            print 'Expected sync sequence = ', expected_sync_sequence[i]
            print 'Auto generator found : '
            print opList
            print paramList
            print syncList
            print '\n\n'
            return True


# A bunch of functions to insert ops into the j-lang file.
def insertUnlink(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    open_file_map.pop(file_name, None)
    return ('unlink', file_name)

def insertRmdir(file_name,open_dir_map, open_file_map, file_length_map, modified_pos):
    open_dir_map.pop(file_name, None)
    return ('rmdir', file_name)

def insertXattr(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    return ('fsetxattr', file_name)

def insertOpen(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    if file_name in FileOptions or file_name in SecondFileOptions:
        open_file_map[file_name] = 1
    elif file_name in DirOptions or file_name in SecondDirOptions or file_name in TestDirOptions:
        open_dir_map[file_name] = 1
    return ('open', file_name)

def insertMkdir(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    if file_name in DirOptions or file_name in SecondDirOptions or file_name in TestDirOptions:
        open_dir_map[file_name] = 0
    return ('mkdir', file_name)

def insertClose(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    if file_name in FileOptions or file_name in SecondFileOptions:
        open_file_map[file_name] = 0
    elif file_name in DirOptions or file_name in SecondDirOptions or file_name in TestDirOptions:
        open_dir_map[file_name] = 0
    return ('close', file_name)

def insertWrite(file_name, open_dir_map, open_file_map, file_length_map, modified_pos):
    if file_name not in file_length_map:
        file_length_map[file_name] = 0
    file_length_map[file_name] += 1
    return ('write', (file_name, 'append'))


#Dependency checks : Creat - file should not exist. If it does, remove it.
def checkCreatDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    file_name = current_sequence[pos][1]
    
    
    #Either open or closed doesn't matter. File should not exist at all
    if file_name in open_file_map:
        #Insert dependency before the creat command
        modified_sequence.insert(modified_pos, insertUnlink(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    return modified_pos

#Dependency checks : Mkdir
def checkDirDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    file_name = current_sequence[pos][1]
    if file_name not in DirOptions and file_name not in SecondDirOptions:
        print 'Invalid param list for mkdir'
    
    #Either open or closed doesn't matter. Directory should not exist at all
    # TODO : We heavily depend on the pre-defined file list. Need to generalize it at some point.
    if file_name in open_dir_map and file_name != 'test':
        #if dir is A, remove contents within it too
        if file_name == 'A':
            if 'A/foo' in open_file_map and open_file_map['A/foo'] == 1:
                file = 'A/foo'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'A/foo' in open_file_map and open_file_map['A/foo'] == 0:
                file = 'A/foo'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            if 'A/bar' in open_file_map and open_file_map['A/bar'] == 1:
                file = 'A/bar'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'A/bar' in open_file_map and open_file_map['A/bar'] == 0:
                file = 'A/bar'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            
            if 'AC' in open_dir_map and open_dir_map['AC'] == 1:
                file = 'AC'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            if 'AC' in open_dir_map:
                if 'AC/foo' in open_file_map and open_file_map['AC/foo'] == 1:
                    file = 'AC/foo'
                    modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1
                    modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1
                elif 'AC/foo' in open_file_map and open_file_map['AC/foo'] == 0:
                    file = 'AC/foo'
                    modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1
                if 'AC/bar' in open_file_map and open_file_map['AC/bar'] == 1:
                    file = 'AC/bar'
                    modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1
                    modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1
                elif 'AC/bar' in open_file_map and open_file_map['AC/bar'] == 0:
                    file = 'AC/bar'
                    modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                    modified_pos += 1

                file = 'AC'
                modified_sequence.insert(modified_pos, insertRmdir(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1


        if file_name == 'B':
            if 'B/foo' in open_file_map and open_file_map['B/foo'] == 1:
                file = 'B/foo'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'B/foo' in open_file_map and open_file_map['B/foo'] == 0:
                file = 'B/foo'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            if 'B/bar' in open_file_map and open_file_map['B/bar'] == 1:
                file = 'B/bar'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'B/bar' in open_file_map and open_file_map['B/bar'] == 0:
                file = 'B/bar'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1

        if file_name == 'AC':
            if 'AC/foo' in open_file_map and open_file_map['AC/foo'] == 1:
                file = 'AC/foo'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'AC/foo' in open_file_map and open_file_map['AC/foo'] == 0:
                file = 'AC/foo'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            if 'AC/bar' in open_file_map and open_file_map['AC/bar'] == 1:
                file = 'AC/bar'
                modified_sequence.insert(modified_pos, insertClose(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            elif 'AC/bar' in open_file_map and open_file_map['AC/bar'] == 0:
                file = 'AC/bar'
                modified_sequence.insert(modified_pos, insertUnlink(file, open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1


        #Insert dependency before the creat command
        modified_sequence.insert(modified_pos, insertRmdir(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
            
    return modified_pos

# Check if parent directories exist, if not create them.
def checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    file_names = current_sequence[pos][1]
    if isinstance(file_names, basestring):
        file_name = file_names
        #Parent dir doesn't exist
        if (Parent(file_name) == 'A' or Parent(file_name) == 'B')  and Parent(file_name) not in open_dir_map:
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
        if Parent(file_name) == 'AC' and Parent(file_name) not in open_dir_map:
            if Parent(Parent(file_name)) not in open_dir_map:
                modified_sequence.insert(modified_pos, insertMkdir(Parent(Parent(file_name)), open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
                    
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1



    else:
        file_name = file_names[0]
        file_name2 = file_names[1]
        
        #Parent dir doesn't exist
        if (Parent(file_name) == 'A' or Parent(file_name) == 'B')  and Parent(file_name) not in open_dir_map:
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
        
        if Parent(file_name) == 'AC' and Parent(file_name) not in open_dir_map:
            if Parent(Parent(file_name)) not in open_dir_map:
                modified_sequence.insert(modified_pos, insertMkdir(Parent(Parent(file_name)), open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1

        #Parent dir doesn't exist
        if (Parent(file_name2) == 'A' or Parent(file_name2) == 'B')  and Parent(file_name2) not in open_dir_map:
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name2), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1

        if Parent(file_name2) == 'AC' and Parent(file_name2) not in open_dir_map:
            if Parent(Parent(file_name2)) not in open_dir_map:
                modified_sequence.insert(modified_pos, insertMkdir(Parent(Parent(file_name2)), open_dir_map, open_file_map, file_length_map, modified_pos))
                modified_pos += 1
            
            modified_sequence.insert(modified_pos, insertMkdir(Parent(file_name2), open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
    
    return modified_pos


# Check the dependency that file already exists and is open, eg. before writing to a file
def checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    file_names = current_sequence[pos][1]
    if isinstance(file_names, basestring):
        file_name = file_names
    else:
        file_name = file_names[0]
    
    # If we are trying to fsync a dir, ensure it exists
    if file_name in DirOptions or file_name in SecondDirOptions or file_name in TestDirOptions:
        if file_name not in open_dir_map:
            modified_sequence.insert(modified_pos, insertMkdir(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
        
        if file_name in open_dir_map and open_dir_map[file_name] == 0:
            modified_sequence.insert(modified_pos, insertOpen(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1


    if file_name in FileOptions or file_name in SecondFileOptions:
        if file_name not in open_file_map or open_file_map[file_name] == 0:
        #Insert dependency - open before the command
            modified_sequence.insert(modified_pos, insertOpen(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
    
    return modified_pos

#Ensures that the file is closed. If not, closes it.
def checkClosed(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    
    file_names = current_sequence[pos][1]
    if isinstance(file_names, basestring):
        file_name = file_names
    else:
        file_name = file_names[0]

    if file_name in open_file_map and open_file_map[file_name] == 1:
        modified_sequence.insert(modified_pos, insertClose(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    
    if file_name in open_dir_map and open_dir_map[file_name] == 1:
        modified_sequence.insert(modified_pos, insertClose(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    return modified_pos

#If the op is remove xattr, we need to ensure, there's atleast one associated xattr to the file
def checkXattr(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    file_name = current_sequence[pos][1]
    if open_file_map[file_name] == 1:
        modified_sequence.insert(modified_pos, insertXattr(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    return modified_pos

# For overwrites ensure that the file is not empty.
def checkFileLength(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    
    file_names = current_sequence[pos][1]
    if isinstance(file_names, basestring):
        file_name = file_names
    else:
        file_name = file_names[0]
    
    # 0 length file
    if file_name not in file_length_map:
        modified_sequence.insert(modified_pos, insertWrite(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    return modified_pos


# Handles satisfying dependencies, for a given core FS op
def satisfyDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map):
    if isinstance(current_sequence[pos], basestring):
        command = current_sequence[pos]
    else:
        command = current_sequence[pos][0]
    
    #    print 'Command = ', command
    
    if command == 'creat' or command == 'mknod':
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkCreatDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        file = current_sequence[pos][1]
        open_file_map[file] = 1
    
    elif command == 'mkdir':
        modified_pos = checkDirDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        dir = current_sequence[pos][1]
        open_dir_map[dir] = 0

    elif command == 'falloc':
        file = current_sequence[pos][1][0]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        #if file doesn't exist, has to be created and opened
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        #Whatever the op is, let's ensure file size is non zero
        modified_pos = checkFileLength(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)


    elif command == 'write' or command == 'dwrite' or command == 'mmapwrite':
        file = current_sequence[pos][1][0]
        option = current_sequence[pos][1][1]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        #if file doesn't exist, has to be created and opened
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        
        #if we chose to do an append, let's not care about the file size
        # however if its an overwrite or unaligned write, then ensure file is atleast one page long
        if option == 'append':
            if file not in file_length_map:
                file_length_map[file] = 0
            file_length_map[file] += 1
#       elif option == 'overlap_unaligned_start' or 'overlap_unaligned_end' or 'overlap_start' or 'overlap_end' or 'overlap_extend':
        elif option == 'overlap' or 'overlap_aligned' or 'overlap_unaligned':
            modified_pos = checkFileLength(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)

        #If we do a dwrite, let's close the file after that
        if command == 'dwrite':
            if file in FileOptions or file in SecondFileOptions:
                open_file_map[file] = 0


    elif command == 'link':
        second_file = current_sequence[pos][1][1]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        if second_file in open_file_map and open_file_map[second_file] == 1:
        #Insert dependency - open before the command
            modified_sequence.insert(modified_pos, insertClose(second_file, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
    
        #if we have a closed file, remove it
        if second_file in open_file_map and open_file_map[second_file] == 0:
            #Insert dependency - open before the command
            modified_sequence.insert(modified_pos, insertUnlink(second_file, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
        
        
        #We have created a new file, but it isn't open yet
        open_file_map[second_file] = 0
    
    elif command == 'rename':
        #If the file was open during rename, does the handle now point to new file?
        first_file = current_sequence[pos][1][0]
        second_file = current_sequence[pos][1][1]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        #Checks if first file is closed
        modified_pos = checkClosed(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        if second_file in open_file_map and open_file_map[second_file] == 1:
            #Insert dependency - close the second file
            modified_sequence.insert(modified_pos, insertClose(second_file, open_dir_map, open_file_map, file_length_map, modified_pos))
            modified_pos += 1
        
        #We have removed the first file, and created a second file
        if first_file in FileOptions or first_file in SecondFileOptions:
            open_file_map.pop(first_file, None)
            open_file_map[second_file] = 0
        elif first_file in DirOptions or first_file in SecondDirOptions:
            open_dir_map.pop(first_file, None)
            open_dir_map[second_file] = 0
        

    elif command == 'symlink':
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        #No dependency checks
        pass
    
    elif command == 'remove' or command == 'unlink':
        #Close any open file handle and then unlink
        file = current_sequence[pos][1]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos,open_dir_map, open_file_map, file_length_map)
        modified_pos = checkClosed(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        #Remove file from map
        open_file_map.pop(file, None)


    elif command == 'removexattr':
        #Check that file exists
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        #setxattr
        modified_pos = checkXattr(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
    
    elif command == 'fsync' or command == 'fdatasync' or command == 'fsetxattr':
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)

    elif command == 'none' or command == 'sync':
        pass

    elif command == 'truncate':
        file = current_sequence[pos][1][0]
        option = current_sequence[pos][1][1]
        
        modified_pos = checkParentExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        # if file doesn't exist, has to be created and opened
        modified_pos = checkExistsDep(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
        
        # Put some data into the file
        modified_pos = checkFileLength(current_sequence, pos, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
    
    else:
        print command
        print 'Invalid command'

    return modified_pos

#Helper to merge lists
def flatList(op_list):
    flat_list = list()
    if not isinstance(op_list, basestring):
        for sublist in op_list:
            if not isinstance(sublist, basestring):
                for item in sublist:
                    flat_list.append(item)
            else:
                flat_list.append(sublist)
    else:
        flat_list.append(op_list)

    return flat_list


# Creates the actual J-lang file.
def buildJlang(op_list, length_map):
    flat_list = list()
    if not isinstance(op_list, basestring):
        for sublist in op_list:
            if not isinstance(sublist, basestring):
                for item in sublist:
                    flat_list.append(item)
            else:
                flat_list.append(sublist)
    else:
        flat_list.append(op_list)

    command_str = ''
    command = flat_list[0]
    if command == 'open':
        file = flat_list[1]
        if file in DirOptions or file in SecondDirOptions or file in TestDirOptions:
            command_str = command_str + 'opendir ' + file.replace('/','') + ' 0777'
        else:
            command_str = command_str + 'open ' + file.replace('/','') + ' O_RDWR|O_CREAT 0777'

    if command == 'creat':
        file = flat_list[1]
        command_str = command_str + 'open ' + file.replace('/','') + ' O_RDWR|O_CREAT 0777'

    if command == 'mkdir':
        file = flat_list[1]
        command_str = command_str + 'mkdir ' + file.replace('/','') + ' 0777'

    if command == 'mknod':
        file = flat_list[1]
        command_str = command_str + 'mknod ' + file.replace('/','') + ' TEST_FILE_PERMS|S_IFCHR|S_IFBLK' + ' 0'


    if command == 'falloc':
        file = flat_list[1]
        option = flat_list[2]
        write_op = flat_list[3]
        command_str = command_str + 'falloc ' + file.replace('/','') + ' ' + str(option) + ' '
        if write_op == 'append':
            off = str(length_map[file])
            lenn = '32768'
            length_map[file] += 32768
        elif write_op == 'overlap_unaligned_start':
            off = '0'
            lenn = '5000'
        elif write_op == 'overlap_unaligned_end':
            size = length_map[file]
            off = str(size-5000)
            lenn = '5000'
        elif write_op == 'overlap_extend':
            size = length_map[file]
            off = str(size-2000)
            lenn = '5000'
            length_map[file] += 3000
        
        command_str = command_str + off + ' ' + lenn

    if command == 'write':
        file = flat_list[1]
        write_op = flat_list[2]
        command_str = command_str + 'write ' + file.replace('/','') + ' '
        if write_op == 'append':
            lenn = '32768'
            if file not in length_map:
                length_map[file] = 0
                off = '0'
            else:
                off = str(length_map[file])
            
            length_map[file] += 32768
        
        elif write_op == 'overlap_unaligned_start':
            off = '0'
            lenn = '5000'
        elif write_op == 'overlap_unaligned_end':
            size = length_map[file]
            off = str(size-5000)
            lenn = '5000'
        elif write_op == 'overlap_extend':
            size = length_map[file]
            off = str(size-2000)
            lenn = '5000'
        
        command_str = command_str + off + ' ' + lenn

    if command == 'dwrite':
        file = flat_list[1]
        write_op = flat_list[2]
        command_str = command_str + 'dwrite ' + file.replace('/','') + ' '
        
        if write_op == 'append':
            lenn = '32768'
            if file not in length_map:
                length_map[file] = 0
                off = '0'
            else:
                off = str(length_map[file])
            length_map[file] += 32768

        elif write_op == 'overlap_start':
            off = '0'
            lenn = '8192'
        elif write_op == 'overlap_end':
            size = length_map[file]
            off = str(size-8192)
            lenn = '8192'

        command_str = command_str + off + ' ' + lenn
    
    if command == 'mmapwrite':
        file = flat_list[1]
        write_op = flat_list[2]
        ret = flat_list[3]
        command_str = command_str + 'mmapwrite ' + file.replace('/','') + ' '
        
        if write_op == 'append':
            lenn = '32768'
            if file not in length_map:
                length_map[file] = 0
                off = '0'
            else:
                off = str(length_map[file])
            length_map[file] += 32768
        
        elif write_op == 'overlap_start':
            off = '0'
            lenn = '8192'
        elif write_op == 'overlap_end':
            size = length_map[file]
            off = str(size-8192)
            lenn = '8192'
        
        command_str = command_str + off + ' ' + lenn + '\ncheckpoint ' + ret

    

    if command == 'link' or command =='rename' or command == 'symlink':
        file1 = flat_list[1]
        file2 = flat_list[2]
        command_str = command_str + command + ' ' + file1.replace('/','') + ' ' + file2.replace('/','')

    if command == 'unlink'or command == 'remove' or command == 'rmdir' or command == 'close' or command == 'fsetxattr' or command == 'removexattr':
        file = flat_list[1]
        command_str = command_str + command + ' ' + file.replace('/','')

    if command == 'fsync':
        file = flat_list[1]
        ret = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + '\ncheckpoint ' + ret

    if command =='fdatasync':
        file = flat_list[1]
        ret = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + '\ncheckpoint ' + ret


    if command == 'sync':
        ret = flat_list[1]
        command_str = command_str + command + '\ncheckpoint ' + ret

    if command == 'none':
        command_str = command_str + command


    if command == 'truncate':
        file = flat_list[1]
        trunc_op = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + ' '
        if trunc_op == 'aligned':
            len = '0'
            length_map[file] = 0
        elif trunc_op == 'unaligned':
            len = '2500'
        command_str = command_str + len

    return command_str


def getSyncOptions(file_list):
    
    d = list(file_list)
    fsync = ('fsync',)
    sync = ('sync')
    none = ('none')
    SyncSet = list()
    SyncSet.append(none)
    for i in xrange(0, len(d)):
        tup = list(fsync)
        tup.append(d[i])
        SyncSet.append(tuple(tup))
    SyncSet.append(sync)
    return SyncSet    
    
def generatePerm(length):
    perm = list()
    #randomly select the operations to test
    for i in range(0, length):
      perm.append(random.choice(OperationSet))
    return perm  
    
def generateParams(perm):
    currentParameterOption = list() 
    for op in perm:  
      currentParameterOption.append(random.choice(parameterList[op]))
    return currentParameterOption
  
def generateSyncOptions(currentParameterOption):  
    sync = list()
    count_sync = 0
    usedFiles = list()
    flat_used_list = flatList(currentParameterOption)
    for file_len in xrange(0, len(flat_used_list)):
      if isinstance(flat_used_list[file_len], basestring):
        usedFilesList = list(set(flat_used_list) & set(FileOptions + SecondFileOptions + DirOptions + SecondDirOptions + TestDirOptions))
        usedFiles.append(tuple(usedFilesList))
    usedFiles = flatList(set(usedFiles))
    return getSyncOptions(file_range(usedFiles))
    
def generateSync(syncPermutationsCustom, perm):
    sync = list()
    for index in range(0, len(perm)):
      if perm[index] == 'fdatasync' or perm[index] == 'mmapwrite':
        sync.append('')
      else:
        lowerbound = 1 if (index == len(perm) - 1) else 0
        sync.append(syncPermutationsCustom[random.randint(lowerbound, len(syncPermutationsCustom)) - 1])
    return sync
    
  
def generateSeq(perm, currentParameterOption, sync):
    seq = list()
    #merge the lists here . Just check if perm has fdatasync. If so skip adding any sync:
    for length in xrange(0, len(perm)):
      skip_sync = False
      op = list()
      if perm[length] == 'fdatasync' or perm[length] == 'mmapwrite':
        skip_sync = True
        isFadatasync = True
      else:
        op.append(perm[length])

      if skip_sync:
        op.append(perm[length])
        op.append(currentParameterOption[length])
        if length == len(perm)-1:
          op.append('1')
        else:
          op.append('0')
        op = tuple(flatList(op))

      else:
        op.append(currentParameterOption[length])
                
      seq.append(tuple(op))

      if not skip_sync:
        sync_op = list()
        sync_op.append(sync[length])
        if length == len(perm)-1:
          sync_op.append('1')
        else:
          sync_op.append('0')
        seq.append(tuple(flatList(sync_op)))
    
    return seq    
    
    
def generateModifiedSequence(seq):
    # **PHASE 4** : Deterministic stage - satisfy dependencies for all ops in the list so far.
    modified_pos = 0
    modified_sequence = list(seq)
    open_file_map = {}
    file_length_map = {}
    open_dir_map = {}

    #test dir exists
    open_dir_map['test'] = 0

    # Go over the current sequence of operations and satisfy dependencies for each file-system op
    for i in xrange(0, len(seq)):
      modified_pos = satisfyDep(seq, i, modified_sequence, modified_pos, open_dir_map, open_file_map, file_length_map)
      modified_pos += 1
        
    #now close all open files
    for file_name in open_file_map:
      if open_file_map[file_name] == 1:
        modified_sequence.insert(modified_pos, insertClose(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    
    #close all open directories
    for file_name in open_dir_map:
      if open_dir_map[file_name] == 1:
        modified_sequence.insert(modified_pos, insertClose(file_name, open_dir_map, open_file_map, file_length_map, modified_pos))
        modified_pos += 1
    return modified_sequence
    
class SlowBar(FillingCirclesBar):
    suffix = '%(percent).0f%%  (Completed %(index)d skeletons with %(global_count)d workloads)'
    @property
    def global_count(self):
        return global_count
        
param_num_max = 0
op_num_max = 0        
        
def getSequenceNum(perm, paramlist, syncList, syncOptions):
  global param_num_max
  global op_num_max
  seq_num = list()
  syncOptions_max = 2
  #print("sync op max", syncOptions_max)
  for index in range(0, len(perm)):
    op = perm[index]
    param = paramlist[index]
    sync = syncList[index]
    op_num = OperationSet.index(op) + 1
    param_num = parameterList[op].index(param) + 1
    val = ( str(op_num).ljust(op_num_max,'0') + str(param_num).ljust(param_num_max,'0'))
    sync_num = str('00') if sync == '' else str(syncOptions.index(sync) + 1).ljust(syncOptions_max, '0')
    #print(op_num)
    #print(param_num)
    #print(sync_num)
    val += sync_num
    seq_num.append(int(val))
  #print (seq_num)  
  return seq_num   




def djb2(seq_num):
  hash_val = 5381
  for i in seq_num:
    hash_val = ((hash_val << 5) + hash_val) + i; # hash_val * 33 + i 
  return hash_val



def sdbm(seq_num):
  hash_val = 0
  for i in seq_num:
    hash_val = i + (hash_val << 6) + (hash_val << 16) - hash_val;
  return hash_val



sequence_storage = []

bloomFilter = []
bloomFilter_size = 163840
hits = 0
false_positive = 0
false_negative = 0
filledSpaces = 0

def longCheck(seq_num):
  if seq_num not in sequence_storage:
    sequence_storage.append(seq_num)
    return True
  return False

def longAdd(seq_num):
    sequence_storage.append(seq_num)

def createBloomFilter():
  global bloomFilter
  bloomFilter = [False] * bloomFilter_size

def installBloomEntry(perm, param, syncList, syncOptions):
  global hits
  global false_positive
  global false_negative
  global filledSpaces
  seq_num = getSequenceNum(perm, param, syncList, syncOptions)
  djb2_val = djb2(seq_num) % bloomFilter_size
  sbdm_val = sdbm(seq_num) % bloomFilter_size
  if(bloomFilter[djb2_val] and bloomFilter[sbdm_val]):
    #hits += 1
    result = longCheck(seq_num)
    if(result):
      #false_negative += 1
      return True
    return False
  longAdd(seq_num) 
  #if(not bloomFilter[djb2_val]):
  #  filledSpaces +=1
  bloomFilter[djb2_val] = True
  #if(not bloomFilter[sbdm_val]):
  #  filledSpaces +=1
  bloomFilter[sbdm_val] = True
  return True

def bloomFull():
  for b in bloomFilter:
    if (not b):
      return False
global_count = 0
parameterList = {}
SyncSet = list()
num_ops = 0
nested = False
demo = False
syncPermutations = []
count = 0
permutations = []
log_file_handle = 0
count_param = 0
dest_dir = ""


def setup():
    global global_count
    global parameterList
    global num_ops
    global syncPermutations
    global count
    global nested
    global permutations
    global SyncSet
    global demo
    global log_file_handle
    global count_param
    global FileOptions
    global SecondFileOptions
    global SecondDirOptions
    global OperationSet
    global FallocOptions
    global bloomFilter
    global dest_dir
    global jlang_output
    global param_num_max
    global op_num_max
    createBloomFilter()
    global_count = 0
    dest_dir = "fuzzer"
    target_path = '../code/tests/' + dest_dir + '/j-lang-files/'
    if not os.path.exists(target_path):
        os.makedirs(target_path)
    for i in OperationSet:
        parameterList[i] = buildTuple(i)
    dest_j_lang_file = '../code/tests/' + dest_dir + '/base-j-lang'
    source_j_lang_file = '../code/tests/ace-base/base-j-lang'
    copyfile(source_j_lang_file, dest_j_lang_file)
    
    dest_j_lang_cpp = '../code/tests/' + dest_dir + '/base.cpp'
    source_j_lang_cpp = '../code/tests/ace-base/base.cpp'
    copyfile(source_j_lang_cpp, dest_j_lang_cpp) 
    
    op_num_max = len(str(len(OperationSet) + 1))
    param_num_max = 0
    for op in OperationSet:
      if( len(str(len(parameterList[op]) + 1)) > param_num_max):
        param_num_max = len(str(len(parameterList[op]) + 1))
    #print(op_num_max)
    #print(param_num_max)
              

def generateJLang(modified_sequence):
    j_lang_file = 'j-langf' + str(global_count)
    source_j_lang_file = '../code/tests/' + dest_dir + '/base-j-lang'
    copyfile(source_j_lang_file, j_lang_file)
    length_map = {}
    with open(j_lang_file, 'a') as f:
        run_line = '\n\n# run\n'
        f.write(run_line)
        
        for insert in xrange(0, len(modified_sequence)):
          cur_line = buildJlang(modified_sequence[insert], length_map)
          cur_line_log = '{0}'.format(cur_line) + '\n'
          f.write(cur_line_log)

    f.close()
    exec_command = 'python ../ace/cmAdapter.py -b ../code/tests/' + dest_dir + '/base.cpp -t ' + j_lang_file + ' -p ../code/tests/' + dest_dir + '/ -o ' + str(global_count)
    subprocess.call(exec_command, shell=True)
    mv_command = 'mv ' + j_lang_file + ' ../fuzzer/tests/'
    subprocess.call(mv_command, shell=True)
    return j_lang_file

def produceWorkload(upper_bound):
    global global_count
    num_ops = random.randint(4, upper_bound)
    perm = generatePerm(int(num_ops))
    param = generateParams(perm)
    syncOptions = generateSyncOptions(param)
    syncList = generateSync(syncOptions, perm)
    while(not installBloomEntry(perm, param, syncList, syncOptions)):
      num_ops = random.randint(4, upper_bound)
      perm = generatePerm(int(num_ops))
      param = generateParams(perm)
      syncOptions = generateSyncOptions(param)
      syncList = generateSync(syncOptions, perm)
      if bloomFull():
        break
    seq = generateSeq(perm, param,syncList)    
      
    modified_seq = generateModifiedSequence(seq)
      #print(bloomFilter)
    #print ("done") 
    #print ("hits:" + str(hits))
    if (bloomFull()):
      return ''
    #print(bloomFilter_size - filledSpaces)  
    #print (modified_seq)
    jlang = ''
    jlang = generateJLang(modified_seq)
    global_count += 1
    return jlang

def main():
    parsed_args = build_parser().parse_args()
    setup()
    for i in range(int(parsed_args.amount)):
      val = produceWorkload(int(parsed_args.sequence_len))
      if val == '':
        break;
    print (false_negative)  

if __name__ == '__main__':
	main()
