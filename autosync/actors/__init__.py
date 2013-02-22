class Connection(object):

    def __init__(self, container, prefix):
        self.connection = self.get_connection()
        self.container = self.get_container(container, prefix)

    def __call__(self):
        return self.get_connection()

    def get_container(self):
        return Container(self.connection, 
                         self.container, self.prefix)



class Container(object):
    def __init__(self, connection, container, prefix):
        self.connection = connection
        self.container = container
        self.prefix = prefix


