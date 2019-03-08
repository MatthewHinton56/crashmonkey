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
from shutil import copyfile
from string import maketrans
from multiprocessing import Pool
import filesys
import trim_workload

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
DirOptions = ['A/']
TestDirOptions = ['test']
SecondDirOptions = ['B/']


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

expected_sequence.append([('link', ('foo', 'bar')), ('unlink', ('bar')), ('creat', ('bar'))])
expected_sync_sequence.append([('sync'), ('none'), ('fsync', 'bar')])


# 2. btrfs_rename_special_file 3 (yes in 3)
expected_sequence.append([('mknod', ('foo')), ('rename', ('foo', 'bar')), ('link', ('bar', 'foo'))])
expected_sync_sequence.append([('fsync', 'bar'), ('none'), ('fsync', 'bar')])

# 3. new_bug1_btrfs 2 (Yes finds in 2)
expected_sequence.append([('write', ('foo', 'append')), ('falloc', ('foo', 'FALLOC_FL_ZERO_RANGE|FALLOC_FL_KEEP_SIZE', 'append'))])
expected_sync_sequence.append([('fsync', 'foo'), ('fsync', 'foo')])

# 4. new_bug2_f2fs 3 (Yes finds in 2)
expected_sequence.append([('write', ('foo', 'append')), ('falloc', ('foo', 'FALLOC_FL_ZERO_RANGE|FALLOC_FL_KEEP_SIZE', 'append')), ('fdatasync', ('foo'))])
expected_sync_sequence.append([('sync'), ('none'), ('none')])

#We miss this in seq-2, because we disallow workloads of sort creat, creat
# 5. generic_034 2
expected_sequence.append([('creat', ('A/foo')), ('creat', ('A/bar'))])
expected_sync_sequence.append([('sync'), ('fsync', 'A')])

# 6. generic_039 2 (Yes finds in 2)
expected_sequence.append([('link', ('foo', 'bar')), ('remove', ('bar'))])
expected_sync_sequence.append([('sync'), ('fsync', 'foo')])

# 7. generic_059 2 (yes finds in 2)
expected_sequence.append([('write', ('foo', 'append')), ('falloc', ('foo', 'FALLOC_FL_PUNCH_HOLE|FALLOC_FL_KEEP_SIZE', 'overlap_unaligned'))])
expected_sync_sequence.append([('sync'), ('fsync', 'foo')])

# 8. generic_066 2 (Yes finds in 2)
expected_sequence.append([('fsetxattr', ('foo')), ('removexattr', ('foo'))])
expected_sync_sequence.append([('sync'), ('fsync', 'foo')])

#Reachable from current seq 2 generator  (#1360 : creat A/foo, rename A,B) (sync, fsync A)
#We will miss this, if we restrict that op2 reuses files from op1
# 9. generic_341 3 (Yes finds in 2)
expected_sequence.append([('creat', ('A/foo')), ('rename', ('A', 'B')), ('mkdir', ('A'))])
expected_sync_sequence.append([('sync'), ('none'), ('fsync', 'A')])

# 10. generic_348 1 (yes finds in 1)
expected_sequence.append([('symlink', ('foo', 'A/bar'))])
expected_sync_sequence.append([('fsync', 'A')])

# 11. generic_376 2 (yes finds in 2)
expected_sequence.append([('rename', ('foo', 'bar')), ('creat', ('foo'))])
expected_sync_sequence.append([('none'), ('fsync', 'bar')])

#Yes reachable from sseeq2 - (falloc (foo, append), fdatasync foo)
# 12. generic_468 3 (yes, finds in 2)
expected_sequence.append([('write', ('foo', 'append')), ('falloc', ('foo', 'FALLOC_FL_KEEP_SIZE', 'append')), ('fdatasync', ('foo'))])
expected_sync_sequence.append([('sync'), ('none'), ('none')])

#We miss this if we sync only used file set - or we need an option 'none' to end the file with
# 13. ext4_direct_write 2
expected_sequence.append([('write', ('foo', 'append')), ('dwrite', ('foo', 'overlap'))])
expected_sync_sequence.append([('none'), ('fsync', 'bar')])

#14 btrfs_EEXIST (Seq 1)
#creat foo, fsync foo
#write foo 0-4K, fsync foo

#btrfs use -O extref during mkfs
#15. generic 041 (If we consider the 3000 as setup, then seq length 3)
#create 3000 link(foo, foo_i), sync, unlink(foo_0), link(foo, foo_3001), link(foo, foo_0), fsync foo

#16. generic 056 (seq2)
#write(foo, 0-4K), fsync foo, link(foo, bar), fsync some random file/dir

#requires that we allow repeated operations (check if mmap write works here)
#17 generic 090 (seq3)
#write(foo 0-4K), sync, link(foo, bar), sync, append(foo, 4K-8K), fsync foo

#18 generic_104 (seq2) larger file set
#link(foo, foo1), link(bar, bar1), fsync(bar)

#19 generic 106 (seq 2)
#link(foo, bar), sync, unlink(bar) *drop cache* fsync foo

#20 generic 107 (seq 3)
#link(foo, A/foo), link(foo, A/bar), sync, unlink(A/bar), fsync(foo)

#21 generic 177
#write(foo, 0-32K), sync, punch_hole(foo, 24K-32K), punch_hole(foo, 4K-64K) fsync foo

#22 generic 321 2 fsyncs?
#rename(foo, A/foo), fsync A, fsync A/foo

#23 generic 322 (yes, seq1)
#rename(A/foo, A/bar), fsync(A/bar)

#24 generic 335 (seq 2) but larger file set
#rename(A/foo, foo), creat bar, fsync(test)

#25 generic 336 (seq 4)
#link(A/foo, B/foo), creat B/bar, sync, unlink(B/foo), mv(B/bar, C/bar), fsync A/foo


#26 generic 342 (seq 3)
# write foo 0-4K, sync, rename(foo,bar), write(foo) fsync(foo)

#27 generic 343 (seq 2)
#link(A/foo, A/bar) , rename(B/foo_new, A/foo_new), fsync(A/foo)

#28 generic 325 (seq3)
#write,(foo, 0-256K), mmapwrite(0-4K), mmapwrite(252-256K), msync(0-64K), msync(192-256K)




def build_parser():
    parser = argparse.ArgumentParser(description='Automatic Crash Explorer - r v0.1')

    # global args
    parser.add_argument('--sequence_len', '-l', default='3', help='Number of critical ops in the bugy workload')
    parser.add_argument('--amount', '-n', default='10', help='Number of Workloads to generate?')
    parser.add_argument('--jlang', '-j', default='False', help='If the jlang file is to be generated')
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

    elif command == 'creat':
        file = flat_list[1]
        command_str = command_str + 'open ' + file.replace('/','') + ' O_RDWR|O_CREAT 0777'

    elif command == 'mkdir':
        file = flat_list[1]
        command_str = command_str + 'mkdir ' + file.replace('/','') + ' 0777'

    elif command == 'mknod':
        file = flat_list[1]
        command_str = command_str + 'mknod ' + file.replace('/','') + ' TEST_FILE_PERMS|S_IFCHR|S_IFBLK' + ' 0'


    elif command == 'falloc':
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

    elif command == 'write':
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

    elif command == 'dwrite':
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
    
    elif command == 'mmapwrite':
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

    

    elif command == 'link' or command =='rename' or command == 'symlink':
        file1 = flat_list[1]
        file2 = flat_list[2]
        command_str = command_str + command + ' ' + file1.replace('/','') + ' ' + file2.replace('/','')

    elif command == 'unlink'or command == 'remove' or command == 'rmdir' or command == 'close' or command == 'fsetxattr' or command == 'removexattr':
        file = flat_list[1]
        command_str = command_str + command + ' ' + file.replace('/','')

    elif command == 'fsync':
        file = flat_list[1]
        ret = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + '\ncheckpoint ' + ret

    elif command =='fdatasync':
        file = flat_list[1]
        ret = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + '\ncheckpoint ' + ret


    elif command == 'sync':
        ret = flat_list[1]
        command_str = command_str + command + '\ncheckpoint ' + ret

    elif command == 'none':
        command_str = command_str + command


    elif command == 'truncate':
        file = flat_list[1]
        trunc_op = flat_list[2]
        command_str = command_str + command + ' ' + file.replace('/','') + ' '
        if trunc_op == 'aligned':
            len = '0'
            length_map[file] = 0
        elif trunc_op == 'unaligned':
            len = '2500'
        command_str = command_str + len
    
    else:
        print 'error: ' + command

    return command_str


def getSyncOptions(file_list):
    
    d = list(file_list)
    fsync = ('fsync',)
    sync = ('sync')
    none = ('none')
    SyncSet = list()
    SyncSet.append(none)
    SyncSet.append(sync)
    for i in xrange(0, len(d)):
        tup = list(fsync)
        tup.append(d[i])
        SyncSet.append(tuple(tup))
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
  
def generateSync(perm):
    sync = list()
    for index in range(0, len(perm)):
      if perm[index] == 'fdatasync' or perm[index] == 'mmapwrite':
        sync.append('')
      else:
        lowerbound = 2 if (index == len(perm) - 1) else 0
        sync.append(syncOptions[random.randint(lowerbound, len(syncOptions) - 1)])
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
    

def satisfyDep(op, modified_seq, root):

    if isinstance(op,  basestring):
        command = op
    else:
        command = op[0]
    if command == 'creat' or command == 'mknod':

        filePath = op[1]
        filesys.preCreat(modified_seq,filePath, root)
        modified_seq.append(op)
        filesys.postCreat(filePath, root)

    elif command == 'mkdir':
        dirPath = op[1]
        filesys.preMkdirKNode(modified_seq, dirPath, root)
        modified_seq.append(op)
        filesys.postMkdirKNode(dirPath, root)

    elif command == 'falloc':
        filePath = op[1][0]
        filesys.preFalloc(modified_seq, filePath, root)
        modified_seq.append(op)
        filesys.postFalloc()

    elif command == 'write' or command == 'dwrite' or command == 'mmapwrite':
        if command == 'mmapwrite':
            filePath = op[1]
            option = op[2]
        else:
            filePath = op[1][0]
            option = op[1][1]
        filesys.preWrite(modified_seq, filePath, option, root)
        modified_seq.append(op)
        filesys.postWrite(filePath, command, root)   

    elif command == 'link':
        filePathOne = op[1][0]
        filePathTwo = op[1][1]
        filesys.preLink(modified_seq, filePathOne, filePathTwo, root)
        modified_seq.append(op)
        filesys.postLink(filePathOne, filePathTwo, root)

    elif command == 'rename':
        filePathOne = op[1][0]
        filePathTwo = op[1][1] 
        filesys.preRename(modified_seq, filePathOne, filePathTwo, root)
        modified_seq.append(op)
        filesys.postRename(filePathOne, filePathTwo, root)

    elif command == 'symlink':
        filePath = op[1][0]
        filesys.preSymLink(modified_seq, filePath, root)
        modified_seq.append(op)
        filesys.postSymLink()    

    elif command == 'remove' or command == 'unlink':
        filePath = op[1]
        filesys.preRemoveUnlink(modified_seq, filePath, root)
        modified_seq.append(op)   
        filesys.postRemoveUnlink(filePath, root)

    elif command == 'removexattr':
        filePath = op[1]
        filesys.preRemovexattr(modified_seq, filePath, root)
        modified_seq.append(op)
        filesys.postRemovexattr(filePath, root)

    elif command == 'fsync' or command == 'fdatasync' or command == 'fsetxattr':     
        filePath = op[1]
        filesys.preFSyncSet(modified_seq, filePath, root)
        modified_seq.append(op)
        filesys.postFSyncSet(command, filePath, root)

    elif command == 'none' or command == 'sync':
        modified_seq.append(op)

    elif command == 'truncate':
        filePath = op[1][0]
        option = op[1][1]   
        filesys.preTruncate(modified_seq, filePath, root)
        modified_seq.append(op)
        filesys.postTruncate(filePath, option, root)

    else:
        print command
        print 'Invalid command'       


def generateModifiedSequence(seq):
    # **PHASE 4** : Deterministic stage - satisfy dependencies for all ops in the list so far.
    modified_sequence = list()
    root = filesys.initialize_filesys()
    filesys.createFile(root, 'test', False)
    #test dir exists

    # Go over the current sequence of operations and satisfy dependencies for each file-system op
    for op in seq:
      modified_pos = satisfyDep(op, modified_sequence, root)
    

    filesys.closeFiles(modified_sequence, root)
    filesys.closeDirectories(modified_sequence, root)
    return modified_sequence

param_num_max = 0
op_num_max = 0        
        
def getSequenceNum(perm, paramlist, syncList):
  global param_num_max
  global op_num_max
  seq_list = []
  syncOptions_max = 2
  #print("sync op max", syncOptions_max)
  for index in range(0, len(perm)):
    op = perm[index]
    param = paramlist[index]
    sync = syncList[index]
    op_num = OperationSet.index(op) + 1
    param_num = parameterList[op].index(param) + 1
    val = ( str(op_num).rjust(op_num_max,'0') + str(param_num).rjust(param_num_max,'0'))
    sync_num = str('00') if sync == '' else str(syncOptions.index(sync) + 1).rjust(syncOptions_max, '0')
    #print(op_num)
    #print(param_num)
    #print(sync_num)
    val += sync_num
    seq_list.append(val)
  #print (seq_num)  
  return ''.join(seq_list)   




def djb2(seq_string):
  hash_val = 5381
  for i in seq_string:
    hash_val = ((hash_val << 5) + hash_val) + ord(i); # hash_val * 33 + i 
  return hash_val



def sdbm(seq_string):
  hash_val = 0
  for i in seq_string:
    hash_val = ord(i) + (hash_val << 6) + (hash_val << 16) - hash_val;
  return hash_val



sequence_storage = set()

bloomFilter = []
bloomFilter_size = 163840
hits = 0
false_positive = 0
false_negative = 0
filledSpaces = 0

def longCheck(seq_string):
  if seq_string not in sequence_storage:
    sequence_storage.add(seq_string)
    return True
  return False

def longAdd(seq_string):
    sequence_storage.add(seq_string)

def createBloomFilter():
  global bloomFilter
  bloomFilter = [False] * bloomFilter_size

def longAndShort(seq_string):
  global hits
  global false_positive
  global false_negative
  global filledSpaces
  djb2_val = djb2(seq_string) % bloomFilter_size
  sbdm_val = sdbm(seq_string) % bloomFilter_size
  python_val = hash(seq_string) % bloomFilter_size
  if(bloomFilter[djb2_val] and bloomFilter[sbdm_val] and bloomFilter[python_val]):
    result = longCheck(seq_string)
    if(result):
      false_negative += 1
      return True
    return False
  longAdd(seq_string) 
  bloomFilter[djb2_val] = True
  bloomFilter[sbdm_val] = True
  bloomFilter[python_val] = True
  return True

def longOnly(seq_string):
  return longCheck(seq_string)  

def shortOnly(seq_string):
  global hits
  global false_positive
  global false_negative
  global filledSpaces
  djb2_val = djb2(seq_string) % bloomFilter_size
  sbdm_val = sdbm(seq_string) % bloomFilter_size
  python_val = hash(seq_string) % bloomFilter_size
  if(bloomFilter[djb2_val] and bloomFilter[sbdm_val] and bloomFilter[python_val]):
    return False
  bloomFilter[djb2_val] = True
  bloomFilter[sbdm_val] = True
  bloomFilter[python_val] = True
  return True

def clean():
  bloomFiler = []
  sequence_storage = set()

def bloomFull():
  for b in bloomFilter:
    if (not b):
      return False


global_count = 0
parameterList = {}
SyncSet = list()
num_ops = 0
demo = False
syncPermutations = []
count = 0
permutations = []
log_file_handle = 0
count_param = 0
dest_dir = ""
syncOptions = []

def setup(nested, resume_f):
    global global_count
    global parameterList
    global num_ops
    global syncPermutations
    global count
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
    global syncOptions
    global workload_count 
    if nested:
      FileOptions = FileOptions + ['A/C/foo']
      SecondFileOptions = SecondFileOptions + ['A/C/bar']
      SecondDirOptions = SecondDirOptions + ['A/C/']
    file_list = list(set(FileOptions + SecondFileOptions + DirOptions + SecondDirOptions + TestDirOptions))    
    syncOptions = getSyncOptions(file_list)    
    global_count = 0
    workload_count = 0
    dest_dir = "fuzzer"
    target_path = './code/tests/' + dest_dir + '/j-lang-files/'
    target_path_seq = './code/tests/' + dest_dir + '/seq-files/'
    if not os.path.exists(target_path):
        os.makedirs(target_path)
    if not os.path.exists(target_path_seq):
        os.makedirs(target_path_seq)
    for i in OperationSet:
        parameterList[i] = buildTuple(i)
    parameterList['rename'].remove(('A/', 'A/C/'))
    dest_j_lang_file = './code/tests/' + dest_dir + '/base-j-lang'
    source_j_lang_file = './code/tests/ace-base/base-j-lang'
    copyfile(source_j_lang_file, dest_j_lang_file)
    
    dest_j_lang_cpp = './code/tests/' + dest_dir + '/base.cpp'
    source_j_lang_cpp = './code/tests/ace-base/base.cpp'
    copyfile(source_j_lang_cpp, dest_j_lang_cpp) 
    
    op_num_max = len(str(len(OperationSet) + 1))
    param_num_max = 0
    for op in OperationSet:
      if( len(str(len(parameterList[op]) + 1)) > param_num_max):
        param_num_max = len(str(len(parameterList[op]) + 1))
    #print(op_num_max)
    #print(param_num_max)
    if(resume_f):
        resume()
              

def generateJLang(modified_sequence):
    j_lang_file = 'j-langf' + str(global_count)
    source_j_lang_file = './code/tests/' + dest_dir + '/base-j-lang'
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
    exec_command = 'python ./ace/cmAdapter.py -b ./code/tests/' + dest_dir + '/base.cpp -t ' + j_lang_file + ' -p ./code/tests/' + dest_dir + '/ -o ' + str(global_count)
    subprocess.call(exec_command, shell=True)
    target_path = ' ./code/tests/' + dest_dir + '/j-lang-files/'
    mv_command = 'mv ' + j_lang_file + target_path
    subprocess.call(mv_command, shell=True)

    return j_lang_file


def writeSeqFile(seq):
    seq_file = 'seqf' + str(global_count)
    with open(seq_file, 'w') as f:
        for op in seq:
            f.write(str(op) + '\n')
    
    f.close()
    target_path = ' ./code/tests/' + dest_dir + '/seq-files/'
    mv_command = 'mv ' + seq_file + target_path
    subprocess.call(mv_command, shell=True)


#embeds known bug sequence into workload
def imbed_sequence(perm, param, syncList, syncOptions):
    bug_work_load_index = random.randint(0, len(expected_sequence))
    bug_sequence = expected_sequence[bug_work_load_index]
    bug_sync = expected_sync_sequence[bug_work_load_index]
    bug_length = len(bug_sequence)
    insert_index = random.randint(1, len(perm) - bug_length)
    for i in range(insert_index, insert_index + bug_length):
        perm[i] = bug_sequence[i - insert_index][0]
        param[i] = bug_sequence[i - insert_index][1]
        syncList[i] = bug_sync[i - insert_index]
        syncOptions.append(bug_sync[i - insert_index])
      
most_recent_seq = []
def produceWorkload(upper_bound, jlang_f, debug):
    global global_count
    global most_recent_seq
    num_ops = random.randint(4, upper_bound)
    perm = generatePerm(int(num_ops))
    param = generateParams(perm)
    syncList = generateSync(perm)
    sequence_num = getSequenceNum(perm, param, syncList)
    while(not longOnly(sequence_num)):
      num_ops = random.randint(4, upper_bound)
      perm = generatePerm(int(num_ops))
      param = generateParams(perm)
      syncList = generateSync(perm)
      sequence_num = getSequenceNum(perm, param, syncList)
    seq = generateSeq(perm, param, syncList)    
    most_recent_seq = seq
    #print(seq)  
    modified_seq_two = trim_workload.generateModifiedSequence(seq)
    modified_seq = generateModifiedSequence(seq)
    print modified_seq
    print modified_seq_two
      #print(bloomFilter)
    #print ("done") 
    #print ("hits:" + str(hits))
    #print(bloomFilter_size - filledSpaces)  
    #print (modified_seq)
    jlang = ' '
    if(debug):
        time_e = time.time()
    if(jlang_f):
      jlang = generateJLang(modified_seq)
      writeSeqFile(seq)
    if(debug):
        print "Jlang: " + str(time.time() - time_e)   
    global_count += 1
    return (jlang, sequence_num)




workload_count = 0
seq_list = list()


def completed_workload(seq_num, add):
    global workload_count 
    if add:
        seq_list.append(seq_num)
    workload_count += 1



def createResumeFile():
    os.remove("resume.txt")
    with open("resume.txt","w") as resume:
        resume.write(str(workload_count) +'\n')
        for line in seq_list:
            if line != '':
                resume.write(line + "\n")
    resume.close()

def resume():
    global global_count
    global workload_count 
    global seq_list
    with open("resume.txt","r") as resume:
        line = resume.readline()
        if(line != ''): 
            global_count = int(line)
            workload_count = global_count
        for line in resume:
                nline = line.replace('\n', '')
                sequence_storage.add(nline)
                seq_list.append(nline)




def main():

    setup(True, False)
    print syncOptions
    file_list = list(set(FileOptions + SecondFileOptions + DirOptions + SecondDirOptions + TestDirOptions))   
    print getSyncOptions(file_list)
    print parameterList['rename']
#    start = time.time()
#    parsed_args = build_parser().parse_args()
#    setup(True, False)
#   avg = 0.0
    for index in range(0, int(5)):
     val = produceWorkload(int(5), False, True)
#      avg += (time.time() - test_start)

#    print false_negative 
#   print time.time() - start
#  print (avg / int(parsed_args.amount))

if __name__ == '__main__':
	main()
