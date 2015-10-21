# LBE - Lite Block Explorer
# Author: Ondrej Sika <ondrej@ondrejsika.com>
# License: MIT <http://ondrejsika.com/license/mit.txt>

import argparse
import binascii

from flask import Flask, render_template
from jsonrpc_requests import Server, TransportError, ProtocolError


parser = argparse.ArgumentParser('LBE - Light Blockchain Explorer')
parser.add_argument('HOST', type=str)
parser.add_argument('PORT', type=int)
parser.add_argument('XCOIND_HOST', type=str)
parser.add_argument('XCOIND_PORT', type=int)
parser.add_argument('XCOIND_USER', type=str)
parser.add_argument('XCOIND_PASSWORD', type=str)
parser.add_argument('--coin', type=str, default='')
parser.add_argument('--debug', action='store_true')

args = parser.parse_args()


class LocalCache(object):
    _storage = None

    def __init__(self):
        self._storage = {}

    def set(self, key, val):
        self._storage[key] = val

    def get(self, key):
        return self._storage.get(key)


class Xcoind(object):
    _rpc = None
    _cache = None

    def __init__(self, host, port, user, password, cache=None):
        self._rpc_server = Server('http://%s:%s' % (host, port), auth=(user, password))
        self._cache = cache if cache else LocalCache()

    def rpc(self, method, *params):
        cachekey = 'rpc__%s_%s' % (method, str(params))
        resp = self._cache.get(cachekey)
        if resp:
            return resp
        resp = self._rpc_server.send_request(method, False, params)
        self._cache.set(cachekey, resp)
        return resp

    def getbestblockhash(self):
        return self.rpc('getbestblockhash')

    def getblock(self, hash):
        return self.rpc('getblock', hash, True)

    def getlastnblocks(self, limit):
        lastblockhash = self.getbestblockhash()
        cachekey = 'getlastnblocks__%s__%s' % (lastblockhash, limit)

        blocks = self._cache.get(cachekey)
        if blocks:
            return blocks

        last = self.getblock(lastblockhash)
        blocks = [last]
        for i in range(limit):
            if not 'previousblockhash' in last:
                break
            last = self.getblock(last['previousblockhash'])
            blocks.append(last)

        self._cache.set(cachekey, blocks)
        return blocks

    def gettx(self, tx_hash):
        raw = self.rpc('getrawtransaction', tx_hash)
        return self.rpc('decoderawtransaction', raw)

    def gettxs(self, tx_hashes):
        cachekey = 'gettxs__%s' % str(tx_hashes)
        txs = self._cache.get(cachekey)
        if txs:
            return txs

        txs = []
        for tx_hash in tx_hashes:
            tx = self.gettx(tx_hash)
            txs.append(tx)

        self._cache.set(cachekey, txs)
        return txs

    def getsimpletx(self, txid):
        tx = self.gettx(txid)
        vins = []
        if 'coinbase' in tx['vin'][0]:
            coinbase = tx['vin'][0]['coinbase']
            coinbase_text = binascii.unhexlify(coinbase)
        else:
            coinbase = None
            coinbase_text = None
            for vin in tx['vin']:
                in_tx = self.gettx(vin['txid'])
                for in_vout in in_tx['vout']:
                    if vin['vout'] == in_vout['n']:
                        vins.append({
                            'address': in_vout['scriptPubKey']['addresses'][0] if 'addresses' in in_vout['scriptPubKey'] else None,
                            'value': in_vout['value'],
                        })

        vouts = []
        for vout in tx['vout']:
            vouts.append({
                'address': vout['scriptPubKey']['addresses'][0] if 'addresses' in vout['scriptPubKey'] else None,
                'value': vout['value'],
            })
        return {
            'txid': txid,
            'is_coinbase': bool(coinbase),
            'coinbase': coinbase,
            'coinbase_text': coinbase_text,
            'vin': vins,
            'vout': vouts,
            'tx': tx,
        }

xcoind = Xcoind(args.XCOIND_HOST, args.XCOIND_PORT, args.XCOIND_USER, args.XCOIND_PASSWORD)

app = Flask(__name__)
app.debug = args.debug


@app.route('/')
def index():
    try:
        blocks = xcoind.getlastnblocks(100)
    except (TransportError, ProtocolError), e:
        print e
        return render_template('error_xcoind.html', coin=args.coin)
    return render_template('index.html', blocks=blocks, coin=args.coin)


@app.route('/block/<hash>')
def block(hash):
    try:
        block = xcoind.getblock(hash)
        coinbase = xcoind.getsimpletx(block['tx'][0])
    except (TransportError, ProtocolError), e:
        print e
        return render_template('error_xcoind.html', coin=args.coin)

    return render_template('block.html', block=block, coinbase=coinbase, coin=args.coin)

@app.route('/tx/<hash>')
def tx(hash):
    try:
        tx = xcoind.getsimpletx(hash)
    except (TransportError, ProtocolError), e:
        print e
        return render_template('error_xcoind.html', coin=args.coin)

    return render_template('tx.html', tx=tx, coin=args.coin)

if __name__ == '__main__':
    app.run(host=args.HOST, port=args.PORT)

