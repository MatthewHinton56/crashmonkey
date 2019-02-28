#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <string>
#include <iostream>
#include <dirent.h>
#include <cstring>
#include <errno.h>
#include <attr/xattr.h>

#include "../BaseTestCase.h"
#include "../../user_tools/api/workload.h"
#include "../../user_tools/api/actions.h"

using fs_testing::tests::DataTestResult;
using fs_testing::user_tools::api::WriteData;
using fs_testing::user_tools::api::WriteDataMmap;
using fs_testing::user_tools::api::Checkpoint;
using std::string;

#define TEST_FILE_PERMS  ((mode_t) (S_IRWXU | S_IRWXG | S_IRWXO))

namespace fs_testing {
    namespace tests {
        
        
        class testName: public BaseTestCase {
            
            public:
            
            virtual int setup() override {
                
				test_path = mnt_dir_ ;
				A_path = mnt_dir_ + "/A";
				AC_path = mnt_dir_ + "/A/C";
				B_path = mnt_dir_ + "/B";
				foo_path = mnt_dir_ + "/foo";
				bar_path = mnt_dir_ + "/bar";
				Afoo_path = mnt_dir_ + "/A/foo";
				Abar_path = mnt_dir_ + "/A/bar";
				Bfoo_path = mnt_dir_ + "/B/foo";
				Bbar_path = mnt_dir_ + "/B/bar";
				ACfoo_path = mnt_dir_ + "/A/C/foo";
				ACbar_path = mnt_dir_ + "/A/C/bar";
                return 0;
            }
            
            virtual int run( int checkpoint ) override {
                
				test_path = mnt_dir_ ;
				A_path =  mnt_dir_ + "/A";
				AC_path =  mnt_dir_ + "/A/C";
				B_path =  mnt_dir_ + "/B";
				foo_path =  mnt_dir_ + "/foo";
				bar_path =  mnt_dir_ + "/bar";
				Afoo_path =  mnt_dir_ + "/A/foo";
				Abar_path =  mnt_dir_ + "/A/bar";
				Bfoo_path =  mnt_dir_ + "/B/foo";
				Bbar_path =  mnt_dir_ + "/B/bar";
				ACfoo_path =  mnt_dir_ + "/A/C/foo";
				ACbar_path =  mnt_dir_ + "/A/C/bar";
				int local_checkpoint = 0 ;

				int fd_foo = cm_->CmOpen(foo_path.c_str() , O_RDWR|O_CREAT , 0777); 
				if ( fd_foo < 0 ) { 
					cm_->CmClose( fd_foo); 
					return errno;
				}


				if ( WriteData ( fd_foo, 0, 32768) < 0){ 
					cm_->CmClose( fd_foo); 
					return errno;
				}


				if ( fallocate( fd_foo , 0 , 32768 , 32768) < 0){ 
					cm_->CmClose( fd_foo);
					 return errno;
				}
				char *filep_foo = (char *) cm_->CmMmap(NULL, 32768 + 32768, PROT_WRITE|PROT_READ, MAP_SHARED, fd_foo, 0);
				if (filep_foo == MAP_FAILED) {
					 return -1;
				}

				int moffset_foo = 0;
				int to_write_foo = 32768 ;
				const char *mtext_foo  = "mmmmmmmmmmklmnopqrstuvwxyz123456";

				while (moffset_foo < 32768){
					if (to_write_foo < 32){
						memcpy(filep_foo + 32768 + moffset_foo, mtext_foo, to_write_foo);
						moffset_foo += to_write_foo;
					}
					else {
						memcpy(filep_foo + 32768 + moffset_foo,mtext_foo, 32);
						moffset_foo += 32; 
					} 
				}

				if ( cm_->CmMsync ( filep_foo + 32768, 8192 , MS_SYNC) < 0){
					cm_->CmMunmap( filep_foo,32768 + 32768); 
					return -1;
				}
				cm_->CmMunmap( filep_foo , 32768 + 32768);


				if ( cm_->CmCheckpoint() < 0){ 
					return -1;
				}
				local_checkpoint += 1; 
				if (local_checkpoint == checkpoint) { 
					return 0;
				}


				int fd_bar = cm_->CmOpen(bar_path.c_str() , O_RDWR|O_CREAT , 0777); 
				if ( fd_bar < 0 ) { 
					cm_->CmClose( fd_bar); 
					return errno;
				}


				if ( cm_->CmClose ( fd_bar) < 0){ 
					return errno;
				}


				if ( remove(bar_path.c_str() ) < 0){ 
					return errno;
				}


				if ( mkdir(A_path.c_str() , 0777) < 0){ 
					return errno;
				}


				if ( mkdir(B_path.c_str() , 0777) < 0){ 
					return errno;
				}


				int fd_B = cm_->CmOpen(B_path.c_str() , O_DIRECTORY , 0777); 
				if ( fd_B < 0 ) { 
					cm_->CmClose( fd_B); 
					return errno;
				}


				if ( cm_->CmFsync( fd_B) < 0){ 
					return errno;
				}


				if ( cm_->CmCheckpoint() < 0){ 
					return -1;
				}
				local_checkpoint += 1; 
				if (local_checkpoint == checkpoint) { 
					return 0;
				}


				if ( fsetxattr( fd_foo, "user.xattr1", "val1 ", 4, 0 ) < 0){ 
					return errno;
				}


				cm_->CmSync(); 


				if ( cm_->CmCheckpoint() < 0){ 
					return -1;
				}
				local_checkpoint += 1; 
				if (local_checkpoint == checkpoint) { 
					return 0;
				}


				cm_->CmClose(fd_foo); 
				fd_foo = cm_->CmOpen(foo_path.c_str() , O_RDWR|O_DIRECT|O_SYNC , 0777); 
				if ( fd_foo < 0 ) { 
					cm_->CmClose( fd_foo); 
					return errno;
				}

				void* data_foo;
				if (posix_memalign(&data_foo , 4096, 8192 ) < 0) {
					return errno;
				}

				 
				int offset_foo = 0;
				int to_write_foo = 8192 ;
				const char *text_foo  = "ddddddddddklmnopqrstuvwxyz123456";
				while (offset_foo < 8192){
					if (to_write_foo < 32){
						memcpy((char *)data_foo+ offset_foo, text_foo, to_write_foo);
						offset_foo += to_write_foo;
					}
					else {
						memcpy((char *)data_foo+ offset_foo,text_foo, 32);
						offset_foo += 32; 
					} 
				} 

				if ( pwrite ( fd_foo, data_foo, 8192, 0) < 0){
					cm_->CmClose( fd_foo); 
					return errno;
				}
				cm_->CmClose(fd_foo);

				cm_->CmSync(); 


				if ( cm_->CmCheckpoint() < 0){ 
					return -1;
				}
				local_checkpoint += 1; 
				if (local_checkpoint == checkpoint) { 
					return 0;
				}


				int fd_Abar = cm_->CmOpen(Abar_path.c_str() , O_RDWR|O_CREAT , 0777); 
				if ( fd_Abar < 0 ) { 
					cm_->CmClose( fd_Abar); 
					return errno;
				}


				if ( cm_->CmClose ( fd_Abar) < 0){ 
					return errno;
				}


				if ( remove(Abar_path.c_str() ) < 0){ 
					return errno;
				}


				if ( cm_->CmClose ( fd_B) < 0){ 
					return errno;
				}


                return 0;
            }
            
            virtual int check_test( unsigned int last_checkpoint, DataTestResult *test_result) override {
                
				test_path = mnt_dir_ ;
				A_path =  mnt_dir_ + "/A";
				AC_path =  mnt_dir_ + "/A/C";
				B_path =  mnt_dir_ + "/B";
				foo_path =  mnt_dir_ + "/foo";
				bar_path =  mnt_dir_ + "/bar";
				Afoo_path =  mnt_dir_ + "/A/foo";
				Abar_path =  mnt_dir_ + "/A/bar";
				Bfoo_path =  mnt_dir_ + "/B/foo";
				Bbar_path =  mnt_dir_ + "/B/bar";
				ACfoo_path =  mnt_dir_ + "/A/C/foo";
				ACbar_path =  mnt_dir_ + "/A/C/bar";
                return 0;
            }
                       
            private:
                       
			 string test_path; 
			 string A_path; 
			 string AC_path; 
			 string B_path; 
			 string foo_path; 
			 string bar_path; 
			 string Afoo_path; 
			 string Abar_path; 
			 string Bfoo_path; 
			 string Bbar_path; 
			 string ACfoo_path; 
			 string ACbar_path; 
                       
            };
                       
    }  // namespace tests
    }  // namespace fs_testing
                       
   extern "C" fs_testing::tests::BaseTestCase *test_case_get_instance() {
       return new fs_testing::tests::testName;
   }
                       
   extern "C" void test_case_delete_instance(fs_testing::tests::BaseTestCase *tc) {
       delete tc;
   }
