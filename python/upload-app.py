#!/usr/bin/env python3
import json
import logging
import os
import time
import urllib
from urllib.parse import urljoin, urlencode, urlunsplit
import requests
import logging
import http.client
import argparse

########################################################################################################################
# MASTER_TOKEN = '6f5093eb9a155f96cb2f97148172f923c0c575f5'
# PERSONAL_TOKEN = '439d8f2e3db549553e2183ff7d627762351961c5'
# owner_Name = 'The-Tabcorp-Mobile-Robot-Organization'
# appName = 'TAB-Android-Treble'
# releaseNotes = 'Test Release notes'
# # owner_Name = 'chaniel-yu'
# # appName = 'ChanielTest'
# appFile = '/Users/paulpr/TAB.apk'
########################################################################################################################

ORGANIZATION_NAME = 'The-Tabcorp-Mobile-Robot-Organization'
DEFAULT_DISTRIBUTION_GROUP_NAME = 'Tabcorp Mobile'
BASE_URL = 'https://api.appcenter.ms'
APP_URL = 'v0.1/apps'
ORG_URL = 'v0.1/orgs'
DISTRIBUTION_GROUPS_URL = 'distribution_groups'
UPLOAD_URL = 'uploads/releases'
HEADERS = {'Accept': 'application/json', 'Content-Type': 'application/json'}
HEADERS_UPLOAD = {'Accept': 'application/json', 'Content-Type': 'application/octet-stream'}
UPLOAD_FILE_NAME_KEY = 'ipa'
UPLOAD_FILE_CONTENT = 'TAB.apk'
APP_TYPE = 'application/vnd.android.package-archive'

release_information = {
    "release_id": 0
}


class AppCenter:
    upload_id = 0

    def __init__(self, token: str, app_name: str, owner_name: str = ORGANIZATION_NAME):
        HEADERS['X-API-Token'] = token
        self.app_name = app_name
        self.owner_name = owner_name
        self.distribution_group_name = None
        self.distribution_group_id = None
        self.release_id = 0
        # http.client.HTTPConnection.debuglevel = 1
        # logging.basicConfig()
        # logging.getLogger().setLevel(logging.DEBUG)
        # requests_log = logging.getLogger("requests.packages.urllib3")
        # requests_log.setLevel(logging.DEBUG)
        # requests_log.propagate = True

    def setup_distribution(self, group_name: str = DEFAULT_DISTRIBUTION_GROUP_NAME):
        url = '/'.join([BASE_URL, ORG_URL, ORGANIZATION_NAME, DISTRIBUTION_GROUPS_URL])
        response = requests.get(url, headers=HEADERS)
        groups_data = json.loads(response.content.decode())
        distribution_group = next(item for item in groups_data if item['name'] == group_name)
        self.distribution_group_name = distribution_group['name']
        self.distribution_group_id = distribution_group['id']
        print('Distribute to %s group, group id = %s' % (self.distribution_group_name, self.distribution_group_id))
        url = '/'.join(
            [BASE_URL, ORG_URL, ORGANIZATION_NAME, DISTRIBUTION_GROUPS_URL, self.distribution_group_name, 'apps'])
        response = requests.get(url, headers=HEADERS)
        apps_data = json.loads(response.content.decode())
        in_group = any(item for item in apps_data if item['name'] == self.app_name)
        if not in_group:
            response = requests.post(url, json={'apps': [{'name': self.app_name}]}, headers=HEADERS)
            print('App added into group %s: status = %d' % (self.distribution_group_name, response.status_code))
        else:
            print('Already in %s group' % self.distribution_group_name)

    def upload_app(self, release_info, filename):
        params = json.dumps(release_info).encode()
        url = '/'.join([BASE_URL, APP_URL, self.owner_name, self.app_name, UPLOAD_URL])
        response = requests.post(url, data=params, headers=HEADERS)
        upload_data = json.loads(response.content.decode())
        print('Create upload resource status code:', response.status_code)
        self.set_release_upload_metadata(upload_data, filename)

    def set_release_upload_metadata(self, upload_data, filename):
        upload_domain = upload_data['upload_domain']
        token = upload_data['token']
        url_encoded_token = upload_data['url_encoded_token']
        package_asset_id = upload_data['package_asset_id']
        upload_id = upload_data['id']
        file_size = os.stat(filename).st_size
        print('url_encoded_token,', url_encoded_token)

        params = dict({'file_name': 'TAB.apk', 'file_size': file_size, 'token': urllib.parse.unquote(url_encoded_token),
                       'content_type': APP_TYPE})
        logging.basicConfig(level=logging.DEBUG)
        payload_str = urllib.parse.urlencode(params)

        url = 'https://file.appcenter.ms/upload/set_metadata/' + package_asset_id
        upload_response = requests.post(url=url, params=payload_str, headers=HEADERS)
        print('Upload resource status code:', upload_response.status_code)
        self.upload_chunks(upload_response._content, package_asset_id, filename, url_encoded_token, upload_id)

    def upload_chunks(self, content, package_asset_id, filename, url_encoded_token, upload_id):
        upload_content = json.loads(content)
        chunk_size = upload_content['chunk_size']
        url = 'https://file.appcenter.ms/upload/upload_chunk/' + package_asset_id
        block_number = 1

        with open(filename, "rb") as f:
            while True:
                # for chunk in chunk_list:
                params = dict({'token': urllib.parse.unquote(url_encoded_token), 'block_number': block_number})
                payload_str = urllib.parse.urlencode(params)
                data = f.read(chunk_size)
                if not data:
                    break
                upload_response = requests.post(url, params=payload_str, data=data, headers=HEADERS)
                print('Uploading chunk: ' + str(block_number), upload_response.status_code)
                block_number += 1
        self.update_upload_status(package_asset_id, url_encoded_token, upload_id)

    def update_upload_status(self, package_asset_id, url_encoded_token, upload_id):
        url = 'https://file.appcenter.ms/upload/finished/' + package_asset_id
        params = dict({'token': urllib.parse.unquote(url_encoded_token)})
        payload_str = urllib.parse.urlencode(params)
        upload_response = requests.post(url, params=payload_str, headers=HEADERS)
        print('Updating upload status ', upload_response.status_code)
        self.commit_upload_status(upload_id)

    def commit_upload_status(self, upload_id):
        url = 'https://api.appcenter.ms/v0.1/apps/' + ORGANIZATION_NAME + '/' + appName + '/uploads/releases/' + upload_id
        payload = "{\"upload_status\": \"uploadFinished\"}"
        upload_response = requests.patch(url, data=payload, headers=HEADERS)
        print('Commiting upload status ', upload_response.status_code)

        if 200 <= upload_response.status_code < 300:
            self.get_release_id(upload_id)

    def get_release_id(self, upload_id):
        global release_distinct_id
        while True:
                url = 'https://api.appcenter.ms/v0.1/apps/' + ORGANIZATION_NAME + '/' + appName + '/uploads/releases/' + upload_id
                upload_response = requests.get(url, headers=HEADERS)
                json_release_id = json.loads(upload_response.content)
                if 'release_distinct_id' in json_release_id:
                    release_distinct_id = json_release_id['release_distinct_id']
                    print('get release id status ', upload_response.status_code)
                    break
                else:
                    time.sleep(3)

        if release_distinct_id != 0:
            self.release_app(release_distinct_id, releaseNotes)

    def release_app(self, release_distinct_id, release_notes='Release'):
        url = 'https://api.appcenter.ms/v0.1/apps/' + ORGANIZATION_NAME + '/' + appName + '/releases/' + str(release_distinct_id)
        payload = "{\"destinations\": [{ \"name\": \"%s\"}], \"notify_testers\": true }" % DEFAULT_DISTRIBUTION_GROUP_NAME
        upload_response = requests.patch(url, data=payload, headers=HEADERS)
        print('release app status ', upload_response.status_code)

def compare_key(item):
    return item['id']


parser = argparse.ArgumentParser()
parser.add_argument("--appToken", required=True, type=str)
parser.add_argument("--appName", required=True, type=str)
parser.add_argument("--appFile", required=True, type=str)
parser.add_argument("--releaseNotes", required=True, type=str)
args = parser.parse_args()
appToken = args.appToken
appName = args.appName
appFile = args.appFile
releaseNotes = args.releaseNotes

appCenter = AppCenter(appToken, appName)
appCenter.setup_distribution()
appCenter.upload_app(release_information, appFile)
# appCenter.release_app(releaseNotes)
