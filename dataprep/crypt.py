# -*- coding: utf-8 -*-

import base64
from Crypto import Random
from Crypto.Cipher import XOR
from Crypto.Cipher import AES
import hashlib
import logging
from multiprocessing import Pool
import sys, os
import traceback
import struct
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np

# Config
SEP=';'
AES_BLOCK_SIZE = 16
CHUNK_SIZE = 100          # size of each chunk
MAX_INPUT_ROWS = None      # number of lines to process in the recipe, None if no limit
#VERBOSECHUNKSIZE = 10000   # display log every VERBOSECHUNKSIZE line
NUM_THREADS = 2            # number of parallel threads


COMMON_TRANSFER_SCHEMA = [
    {'name': 'ida1', 'type': 'string'},
    {'name': 'ida2', 'type': 'string'},
    {'name': 'v', 'type': 'string'}
]

TRANSFER_COLUMNS = [c['name'] for c in COMMON_TRANSFER_SCHEMA]

_test_encrypt_decrypt = False


def pad(s):
    """Return a copy of the given string padded with between 1 and `AES_BLOCK_SIZE` characters to make its length a multiple of `AES_BLOCK_SIZE`"""
    padding_length = AES_BLOCK_SIZE - len(s) % AES_BLOCK_SIZE
    return s + padding_length * chr(padding_length)


def unpad(s):
    """Return a copy of the given string with its padding removed"""
    padding_length = ord(s[-1])
    return s[0:-padding_length]


def encrypt_string(key, string):
    padded = pad(string)
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return base64.urlsafe_b64encode(iv + cipher.encrypt(padded))


def decrypt_string(key, string):
    enc = base64.urlsafe_b64decode(string)
    iv = enc[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(enc[16:]))


def encrypt_df(df):
    """Encrypt the given dataframe in-place"""
    global _test_encrypt_decrypt

    month = datetime.today().strftime('%Y%m')
    prev_month = (datetime.today() - relativedelta(months=1)).strftime('%Y%m')

    df['ida1']=df['idv'].apply(lambda x: base64.urlsafe_b64encode(hashlib.sha256((x+month).encode('ascii','ignore')).digest()))
    df['ida2']=df['idv'].apply(lambda x: base64.urlsafe_b64encode(hashlib.sha256((x+prev_month).encode('ascii','ignore')).digest()))
    df['key']=df['key'].apply(lambda x: hashlib.sha256(x.encode('ascii','ignore')).digest())

    if _test_encrypt_decrypt:
        df['v_orig']=df['v']

    df['v']=df.apply(lambda row: encrypt_string(row['key'], row['v'].encode('ascii','ignore')), axis=1)

    if _test_encrypt_decrypt:
#    df['v_crypt']=df.apply(lambda row: encrypt_string(row['hash2'],row['v']), axis=1)
        df['v_decrypt']=df.apply(lambda row: decrypt_string(row['hash2'],row['v']), axis=1)
        df['v_test']=df.apply(lambda row: (row['v_decrypt'] == row['v_orig']), axis=1)

    df = df[['ida1','ida2','v']]
    return df

def chunk_row_range(chunk_index):
    """Return the index of the first and (maximum) last row of the chunk with the given index, in a string"""
    return "%d-%d" % (chunk_index * CHUNK_SIZE + 1, (chunk_index + 1) * CHUNK_SIZE)


def process_chunk(arg):
    """Encrypt the given chunk in-place and return it (for use with Pool.imap_unordered)"""
    i, df = arg

    try:
        encrypt_df(df)
#        if last_row_index % VERBOSECHUNKSIZE == 0:
        print("chunk {} encrypted".format(chunk_row_range(i)))
    except:
        logging.warning("chunk {} failed:".format(chunk_row_range(i)))
        exc_type, exc_obj, exc_tb = sys.exc_info()
        traceback.print_exception(exc_type, exc_obj, exc_tb)

    # Return i and df for writing to the output dataset
    return i, df


def encrypt_file(input_file, output_file, output_schema=COMMON_TRANSFER_SCHEMA, test_encrypt_decrypt=False):
    global _test_encrypt_decrypt
    _test_encrypt_decrypt = test_encrypt_decrypt

    # Write output schema
    if test_encrypt_decrypt:
        output_schema += [
            {'name': 'v_orig', 'type': 'string'},
            {'name': 'v_decrypt', 'type': 'string'},
            {'name': 'v_test', 'type': 'string'}
        ]

    # Read input dataset as a number of fixed-size dataframes
    chunks = pd.read_csv(input_file, sep=SEP, iterator=True, chunksize=CHUNK_SIZE, encoding='utf8', usecols=['idv','key','v'])

    # Encrypt
    df_list=[encrypt_df(df) for df in chunks]
    # print(df_list)
    output_ds=pd.concat(df_list)
    # print(output_ds)
    output_ds.to_csv(output_file, sep=SEP, compression='gzip', header=False, index=False)

def id(df):
    return df

def encrypt_plaq(key, plaintext):
      cipher = XOR.new(key)
      return base64.b64encode(cipher.encrypt(plaintext))

def decrypt_plaq(key, ciphertext):
      cipher = XOR.new(key)
      return cipher.decrypt(base64.b64decode(ciphertext))


if __name__ == '__main__':
    input_dir=sys.argv[1]
    output_dir=sys.argv[2]
    for file in os.listdir(input_dir):
        print(file)
        encrypt_file(os.path.join(input_dir, file), os.path.join(output_dir, file) )
