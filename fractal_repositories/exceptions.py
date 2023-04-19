class RepositoryException(Exception):
    def __init__(self, message: str = "Repository attribute 'entity' not set"):
        super(RepositoryException, self).__init__(message)


class ObjectNotFoundException(Exception):
    def __init__(self, message: str = "Object not found"):
        super(ObjectNotFoundException, self).__init__(message)
