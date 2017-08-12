#ifndef TESTS_DATA_TEST_ERROR_H
#define TESTS_DATA_TEST_ERROR_H

#include <initializer_list>
#include <iostream>
#include <string>

namespace fs_testing {
namespace tests {

namespace {
  static const unsigned int kOldFilePersisted_ = 0;
  static const unsigned int kFileMissing_ = 1;
  static const unsigned int kFileDataCorrupted_ = 2;
  static const unsigned int kFileMetadataCorrupted_ = 3;
  static const unsigned int kOther_ = 4;
}  // namespace

class DataTestResult {
 public:
  enum ErrorType {
    kOldFilePersisted = (1 << kOldFilePersisted_),
    kFileMissing = (1 << kFileMissing_),
    kFileDataCorrupted = (1 << kFileDataCorrupted_),
    kFileMetadataCorrupted = (1 << kFileMetadataCorrupted_),
    kOther = (1 << kOther_),
  };

  void SetError(std::initializer_list<ErrorType> errors);
  std::ostream& PrintErrors(std::ostream& os);
  std::string error_description;

 private:
  unsigned int error_summary_;

};

std::ostream& operator<<(std::ostream& os, DataTestResult::ErrorType err);

}  // namespace tests
}  // namespace fs_testing

#endif  // TESTS_DATA_TEST_ERROR_H
