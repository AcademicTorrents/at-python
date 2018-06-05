import time
import PeersManager
import PeerSeeker
import PiecesManager
import Torrent
import Tracker
import logging
import Queue
from runner import Runner
import logging
import json
import io
import urllib
import os
import bencode


class Client(object):
    def __init__(self):
        self.datastore = os.getcwd() + "/datastore/"

    def set_datastore(self, path):
        self.datastore = path

    def get_torrent_dir(self, hash):
        return self.datastore + hash + '/'

    def get_dataset(self, name):
        url = "http://academictorrents.com/download/" + name
        torrent_path = os.path.join(self.get_torrent_dir(name), name + '.torrent')
        if not os.path.isdir(self.get_torrent_dir(name)):
            os.makedirs(self.get_torrent_dir(name))

        result = urllib.urlretrieve(url, torrent_path)
        contents = bencode.bdecode(open(torrent_path, 'r').read())

        if not os.path.isfile(self.get_torrent_dir(name) + contents['info']['name']):
            # check if anyone has this package
            Runner(torrent_path, self.get_torrent_dir(name)).start()
        return self.get_torrent_dir(name) + contents['info']['name']