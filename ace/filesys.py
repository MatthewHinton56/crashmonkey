from Queue import *

FileOptions = ['test', 'foo', 'bar']
DirOptions = ['A','B','C']

class File_O:
    def __init__(self, name='', parent=None):
        self.name = name
        self.parent = parent
        self.attribute = False
        self.open = False
    
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

#
def findFile(dir, path):
    pathList = splitPath(path)
    name = pathList[len(pathList)-1]
    pathToFile = pathList[:(len(pathList)-1)]
    scan_dir = dir
    for step in pathToFile:
        scan_dir = scan_dir.getChild(step)
    return scan_dir.getChild(name)


def unlinkFile(dir, file):
    path = splitPath(file)
    parentPath = '/'.join(path[:(len(path)-1)])
    parentDir = findFile(dir, parentPath)
    del parentDir[path[len(path)-1]]


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

def createDepency(modified_seq, file, root):
    if hasFile(root, file):
        unlinkFile(root, file)
        modified_seq.append(('unlink', file))


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
    del dir.parent.children[dir.name]


def preCreat(modified_seq, file, root):
    path = splitPath(file)
    parentPath = '/'.join(parentPath[:(len(path)-1)])
    parentExist(modified_seq,parentPath, root)
    createDepency(modified_seq, file, root)

def postCreat(file, root):
    new_file = createFile(root, file, False)
    new_file.open = True

def preMkdir(modified_seq, dir, root):
    if hasFile(root, dir):
        dirDelete(modified_seq, findFile(root, dir))

def postMkdir(file, root):
    new_file = createFile(root, file, True)
    new_file.open = False


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
