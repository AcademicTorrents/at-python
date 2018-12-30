import requests
from pubsub import pub
from collections import defaultdict

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HttpPeer(object):
    def __init__(self, torrent, url, requestQueue):
        self.readBuffer = b""
        self.requestQueue = requestQueue
        self.stopRequested = False
        self.torrent = torrent
        self.url = url
        self.handshake(url)
        self.sess = requests.Session()


    def requestStop(self):
        self.stopRequested = True

    def httpRequest(self):
        while not self.stopRequested:
            httpPeer, pieces_by_file = self.requestQueue.get()
            responses = httpPeer.request_ranges(pieces_by_file)
            if not responses:
                continue
            codes = [response[0].status_code for response in responses.values()]
            if any(code != 206 for code in codes):
                continue
            httpPeer.publish_responses(responses, pieces_by_file)
            self.requestQueue.task_done()

    def handshake(self, url):
        if not url:
            raise Exception
        resp = requests.head(url)
        if resp.headers.get('Accept-Ranges', False):  # if it was a full-url
            self.url = '/'.join(url.split('/')[0:-1]) + '/'
            return
        else:  # maybe we need to construct a full-url
            directory = self.torrent.torrentFile.get('info', {}).get('name')
            some_filename = self.torrent.torrentFile.get('info', {}).get('files', [{'path': ['']}])[0].get('path')[0]
            if url[-1] == '/':
                compound_url = url + directory + '/'
            else:
                compound_url = url + '/' + directory + '/'
            resp = requests.head(compound_url + some_filename)
            if resp.headers.get('Accept-Ranges', False):  # if it wasn't a full-url
                self.url = compound_url
                return
        raise Exception  # if we don't hit either of the above returns, we should raise an exception.

    def get_pieces(self, piecesManager):
        # TODO: Add another way to exit this loop when we don't hit the max size
        size = 0
        temp_size = 0
        max_size_to_download = 5000000
        max_num_pieces = 50
        temp_pieces = []
        pieces = []

        for idx, b in enumerate(piecesManager.bitfield):
            piece = piecesManager.pieces[idx]
            if not b and not piece.finished and piece.getEmptyBlock():
                temp_pieces.append(piece)
                temp_size += piece.pieceSize
                piece.set_all_blocks_pending()

            if size < temp_size:
                size = temp_size
                pieces = temp_pieces

            if size >= max_size_to_download or len(pieces) >= max_num_pieces:
                return pieces

            if b:
                temp_pieces = []
                temp_size = 0
        return pieces

    def request_ranges(self, pieces_by_file):
        responses = {}
        for filename, pieces in pieces_by_file.items():
            start = pieces[0].get_file_offset(filename)
            directory = self.torrent.torrentFile.get('name')
            end = start
            for piece in pieces:
                end += piece.get_file_length(filename)
            try:
                resp = self.sess.get(self.url + filename, headers={'Range': 'bytes=' + str(start) + '-' + str(end)}, verify=False)
            except Exception as e:
                return False
            responses[filename] = (resp, start)
        return responses

    def publish_responses(self, responses, pieces_by_file):
        unique_pieces = set()
        for piece_list in pieces_by_file.values():
            for piece in piece_list:
                unique_pieces.add(piece)
        for piece in unique_pieces:
            if piece.finished:
                continue
            for f in piece.files:
                filename = f.get('path').split('/')[-1]
                resp = responses[filename][0]
                resp_start = responses[filename][1]
                length = piece.get_file_length(filename)
                pieceOffset = piece.get_piece_offset(filename)
                fileOffset = piece.get_file_offset(filename) - resp_start
                piece.pieceData += resp.content[fileOffset: fileOffset + length]
            blockOffset = 0
            for idx in range(int(len(piece.pieceData)/piece.BLOCK_SIZE)):
                block_size = piece.blocks[idx][1]
                pub.sendMessage('PiecesManager.Piece', piece=(piece.pieceIndex, blockOffset, piece.pieceData[blockOffset: blockOffset + block_size]))
                blockOffset += block_size

    def construct_pieces_by_file(self, pieces):
        pieces_by_file = defaultdict(list)
        for piece in pieces:
            for f in piece.files:
                filename = f.get('path').split('/')[-1]
                pieces_by_file[filename].append(piece)
        return pieces_by_file
