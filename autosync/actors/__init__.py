
class Container(object):

    def __init__(self, connection, container, prefix):
        self.connection = connection
        self.container = container
        self.prefix = prefix


class Connection(object):

    def __init__(self, container, prefix):
        self.connection = self.get_connection()
        self.container = container
        self.prefix = prefix

    def __call__(self):
        return self.get_connection()

    Container = Container

    def get_container(self):
        return self.Container(self.connection,
                              self.container, self.prefix)
