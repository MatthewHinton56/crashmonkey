from Queue import *

FileOptions = ['test', 'foo', 'bar']
DirOptions = ['A','B','C']

class File_O:
    def __init__(self, name='', parent=None):
        self.name = name
        self.parent = parent
        self.attribute = False
        self.open = False
        self.length = 0
    
    def __str__(self):
        return 'Name: ' + self.name + ' Parent: ' + self.parent.name + ' Attribute: ' + str(self.attribute) + ' open: ' + str(self.open)

    def getParent(self):
        return self.parent
    
    def setParent(self, parent):
        self.parent = parent
    
    def getPath(self):
        f = self.parent
        return f.getPath() +  self.name 

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.name == other.name and self.parent == other.parent)
        elif isinstance(other, basestring):
            return (self.name == other)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class Directory(File_O):
    def __init__(self, name='', parent=None):
        self.name = name
        self.parent = parent
        self.children = dict()
        self.attribute = False
        self.open = False
        self.length = 0

    def addChild(self, child):
        self.children[child.name] = child
        child.parent = self
    
    def removeChild(self, child):
        if isinstance(child, basestring):
            if child in self.children:
                self.children[child].parent = None
                del self.children[child]
        elif isinstance(child, File_O):
            if child.name in self.children:
                child.parent = None
                del self.children[child.name]
    
    def hasChild(self, child):
        if isinstance(child, basestring):
            return child in self.children
        elif isinstance(child, File_O):
            return child.name in self.children      

    def getChild(self, child):
        return self.children[child]

    def getPath(self):
        if self.parent.name == '/':
            return self.name + '/'
        f = self.parent
        return f.getPath() +  self.name + '/'


def splitPath(path):
    splitPath = path.split('/')
    if '' in splitPath:
        splitPath.remove('')
    return splitPath 

def hasFile(dir, path):
    pathList = splitPath(path)
    scan_dir = dir
    for step in pathList:
        if not scan_dir.hasChild(step):
            return False
    return True
   

#Pre files along path exist
def createFile(dir, path, is_dir):
    pathList = splitPath(path)
    name = pathList[len(pathList)-1]
    pathToFile = pathList[:(len(pathList)-1)]
    scan_dir = dir
    for step in pathToFile:
        scan_dir = scan_dir.getChild(step)  
    if is_dir:
        new_dir = Directory(name, None)
        scan_dir.addChild(new_dir)
        return new_dir
    else:
        new_file = File_O(name, None)
        scan_dir.addChild(new_file)
        return new_file


def findFile(dir, path):
    pathList = splitPath(path)
    name = pathList[len(pathList)-1]
    pathToFile = pathList[:(len(pathList)-1)]
    scan_dir = dir
    for step in pathToFile:
        scan_dir = scan_dir.getChild(step)
    return scan_dir.getChild(name)


def unlinkFile(dir, filePath):
    path = splitPath(filePath)
    parentPath = '/'.join(path[:(len(path)-1)])
    parentDir = findFile(dir, parentPath)
    parentDir.removeChild(path[len(path) - 1])


def checkExistsDep(modified_seq, filePath, root):
    bool is_dir = filePath.endswith('/')
    if is_dir:
        if not hasFile(root, filePath):
            dir = createFile(root, filePath, True)
            modified_seq.append(('mkdir', filePath))
        else:
            dir = findFile(root, filePath)    
        if not dir.open:
            dir.open = True
            modified_seq.append(('opendir', filePath))
        return dir
    else:
        if not hasFile(root, filePath):
            file = createFile(root, filePath, False)
        else
            file = findFile(root, filePath)
        if not file.open:
            file.open = True
        modified_seq.append(('open', filePath))
        return file


def writeDependency(modified_seq, filePath, root):
    file = findFile(root, filePath)
    if file.length == 0:
        file.length += 1
        modified_seq.append(('write', (filePath, 'append')))


root = None
def initialize_filesys():
    global root
    root = Directory('/', None)

def parentExist(modified_seq, parentPath, root):
    path = splitPath(parentPath)
    test = ''
    for step in path:
        test += step + '/'
        if not hasFile(root, test):
            modified_seq.append(('mkdir', test))
            createFile(root, test, True) 

def createDependency(modified_seq, filePath, root):
    if hasFile(root, filePath):
        unlinkFile(root, filePath)
        modified_seq.append(('unlink', filePath))


def closeAndUnlink(modified_seq, filePath, root, unlink):
    if hasFile(root, filePath):
        file = findFile(root, filePath)
        if file.open:
            file.open = False
            modified_seq.append(('close', filePath))
        if unlink:
            file.parent.removeChild(file)
            modified_seq.append(('unlink', filePath))

def printFileSys(root):
    q = Queue()
    for child in root.children:
        q.put(root.children[child])
    while not q.empty():
        f = q.get()
        print f
        if isinstance(f, Directory):
            for child in f.children:
                q.put(f.children[child])

def dirDeleteHelper(modified_seq, dir):
    for child_name in dir.children:
        child = dir.getChild(child_name)
        if child.open:
            child.open = False
            modified_seq.append(('close', child.getPath()))
        if isinstance(child, Directory): 
            dirDeleteHelper(modified_seq, child)
        else:
            modified_seq.append(('unlink', child.getPath()))
    dir.children = {}
    modified_seq.append(('rmdir', dir.getPath()))


def dirDelete(modified_seq, dir):
    dirDeleteHelper(modified_seq, dir)
    dir.parent.removeChild(dir)


def preCreat(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq,parentPath, root)
    createDependency(modified_seq, filePath, root)

def postCreat(filePath, root):
    new_file = createFile(root, filePath, False)
    new_file.open = True

def preMkdirKNode(modified_seq, dirPath, root):
    if hasFile(root, dirPath):
        dirDelete(modified_seq, findFile(root, dirPath))

def postMkdirKNode(filePath, root):
    new_file = createFile(root, filePath, True)
    new_file.open = False

def preFalloc(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq,parentPath, root)
    checkExistsDep(modified_seq, filePath, root)
    writeDependency(modified_seq, filePath, root)

def postFalloc():
    pass

def preWrite(modified_seq, filePath,command, option, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPath, root)
    file = checkExistsDep(modified_seq, filePath, root)
    if option == 'append':
        file.length += 1
     elif option == 'overlap' or 'overlap_aligned' or 'overlap_unaligned':
        writeDependency(modified_seq, filePath, root)
    if command == 'dwrite':
        file.open = False

def postWrite():
    pass

def preLink(modified_seq, filePathOne, filePathTwo, root):
    pathOne = splitPath(filePathOne)
    parentPathOne = '/'.join(parentPathOne[:(len(path)-1)])
    parentExist(modified_seq, parentPathOne, root)
    pathTwo = splitPath(filePath)
    parentPathTwo = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPathTwo, root)
    checkExistsDep(modified_seq, filePathOne, root)
    closeAndUnlink(modified_seq, filePathTwo, root, True)

def postLink(filePathOne, filePathTwo, root):
    createFile(root, filePathTwo, False)

def preRename(modified_seq, filePathOne, filePathTwo, root):
    pathOne = splitPath(filePathOne)
    parentPathOne = '/'.join(parentPathOne[:(len(path)-1)])
    parentExist(modified_seq, parentPathOne, root)
    pathTwo = splitPath(filePath)
    parentPathTwo = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPathTwo, root)
    checkExistsDep(modified_seq, filePathOne, root)
    closeAndUnlink(modified_seq, filePathTwo, root, False)

def postRename(filePathOne, filePathTwo, root):
    file = findFile(root, filePathOne)
    file.parent.removeChild(file)
    createFile(root, filePathTwo, False)

def preSymLink(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq,parentPath, root)

def postSymLink():
    pass

def preRemoveUnlink(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPath, root)
    checkExistsDep(modified_seq, filePath, root)
    closeAndUnlink(modified_seq, filePath, root, False)    

def postRemoveUnlink(filePath, root):
    file = findFile(root, filePath)
    file.parent.removeChild(file)

def preRemovexattr(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPath, root)
    file = checkExistsDep(modified_seq, filePath, root)
    if not file.attribute:
        file.attribute = True
        modified_seq.append(('fsetxattr', filePath))

def postRemovexattr(filePath, root):
    file = findFile(root, filePath)
    file.attribute = False

def preFSyncSet(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq, parentPath, root)
    file = checkExistsDep(modified_seq, filePath, root)

def postFSyncSet(command, filePath, root):
    if command == 'fsetxattr':
        file = findFile(root, filePath)
        file.attribute = True

def preTruncate(modified_seq, filePath, root):
    path = splitPath(filePath)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq,parentPath, root)
    checkExistsDep(modified_seq, filePath, root)
    writeDependency(modified_seq, filePath, root)

def postTruncate(filePath, root, option):
    if command == 'aligned':
        file = findFile(root, filePath)
        file.length = 0



def main():
    foo = File_O('foo', None)
    root = Directory('/', None)
    A = Directory('A', None)
    B = Directory('B', None)
    B.open = True
    root.addChild(A)
    A.addChild(foo)
    A.addChild(B)
    print foo.getPath()
    print A == 'A'
    print 'A/B/C/'
    print hasFile(A, 'B')
    createFile(root, 'A/B/foo', False)
    print B.children['foo']
    test = 'fsd'
    print test[len(test)+1:len(test)]
    testList = []
    parentExist(testList, 'D/C/', root)
    print root.children['D']
    print root.children['D'].children['C'].getPath()
    print testList
    test = 'A/B/C/foo'
    l = test.split('/')
    print l
    print findFile(root, 'A')
    printFileSys(root)
    testList = []
    dirDelete(testList, A)
    print testList
    print 'A/'.split('/')
    printFileSys(root)   

if __name__ == '__main__':
	main()
