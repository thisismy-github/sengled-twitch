###
##
# Basic shell of an IRC bot that can actually find and read the "custom-reward-id" tag, since
# doing this in a sensible manner is apparently too complex for the Twitch devs. They couldn't
# even be bothered to update their documentation to include "custom-reward-id".
#
# random unrelated link that seems to list all the functions you can override:
# https://pytwitcherapi.readthedocs.io/en/latest/reference/pytwitcherapi.chat.client/pytwitcherapi.chat.client.IRCClient.html
##
###

# TODO: use devices AND colored?
# TODO: revise black? (off doesnt work with thread)
# TODO: revise cfg
# TODO: add gui

from irc.bot import SingleServerIRCBot
from irc.schedule import DefaultScheduler
from colour import Color
from random import randint
import requests, time, threading, sengled
import cfg


class SengledRewardBot(SingleServerIRCBot):
    def __init__(self):
        self.HOST = "irc.chat.twitch.tv"
        self.PORT = 6667

        # Fill in this fields in cfg.py
        self.CLIENT_ID = cfg.CLIENT_ID.lower()
        self.OAUTH = cfg.OAUTH.lower().replace('oauth:', '')
        self.SENGLED_EMAIL = cfg.SENGLED_EMAIL
        self.SENGLED_PASS = cfg.SENGLED_PASS
        self.BOT_NAME = cfg.BOT_NAME.lower()
        self.TARGET_CHANNEL = f"#{cfg.TARGET_CHANNEL.lower()}"

        url = f"https://api.twitch.tv/kraken/users?login={self.BOT_NAME}"
        headers = {"Client-ID": self.CLIENT_ID, "Accept": "application/vnd.twitchtv.v5+json"}
        resp = requests.get(url, headers=headers).json()
        self.channel_id = resp["users"][0]["_id"]

        super().__init__([(self.HOST, self.PORT, f"oauth:{self.OAUTH}")], self.BOT_NAME, self.BOT_NAME)

        self.sengled_api = sengled.api(username=self.SENGLED_EMAIL, password=self.SENGLED_PASS)
        self.devices = self.sengled_api.get_device_details()    # all your devices are colored
        self.colored = self.sengled_api.filter_colored_lamps()
        self.bulbOrder = [self.devices[0], self.devices[2], self.devices[1]]

        self.activeLightRequests = []
        self.lightEffectThreads = [None, None, None]


    # unused but I didn't delete it because reasons
    def send_message(self, message):
        self.connection.privmsg(self.TARGET_CHANNEL, message)


    # runs when bot starts
    def on_welcome(self, connection, event):
        for req in ("membership", "tags", "commands"):
            connection.cap("REQ", f":twitch.tv/{req}")
        connection.join(self.TARGET_CHANNEL)
        print(f"Online in {self.TARGET_CHANNEL}'s channel. Ready for rewards.")

    def on_privmsg(self, connection, event):
        print("\n\nPRIVMSG:")
        print(event)

    ###########################################
    ### runs when messages are sent in chat ###
    ###########################################
    def on_pubmsg(self, connection, event):
        tags = {kvpair["key"]: kvpair["value"] for kvpair in event.tags}
        user = {"name": tags["display-name"], "id": tags["user-id"]}
        message = event.arguments[0]
        if user['name'] == 'streamlabs' and message.startswith('Thank you for the follow'):
            print('\n\n--- FOLLOW DETECTED ---\n\n')


        if "custom-reward-id" in tags and tags["custom-reward-id"] in ("f6932b0f-f218-447e-9158-28677ce90976", "cc3f2f61-5960-452a-b22f-57d81b9b7628"):
            print(f'------------------------------\n{user}: {message}\n------------------------------')


            commands = message.lower().split(';')[:len(self.bulbOrder)]
            changeAllLights = True if len(commands) == 1 else False
            pendingRequests = []

            for bulbNumber, (bulb, command) in enumerate(zip(self.bulbOrder, commands)):
                if command:
                    request = LightRequest(self)

                    # cuts out unneeded characters for more lenient formatting
                    if command[0].isdigit():    # starts with number, assume it's RGB
                        for extraneousCharacter in ('`~!@#$%^&*()_=+[{]}\\|;:\'"<>/?abcdefghijklmnopqrstuvwxyz'):
                            command = command.replace(extraneousCharacter, '')
                    command = command.replace('.', ' ')
                    command = command.replace('-', ' ')
                    command = command.replace(',', ' ')
                    while '  ' in command:  # reduces double-spaces to single-spaces
                        command = command.replace('  ', ' ')

                    commandValues = command.split()
                    colorValue = None

                    # colorName and colorBrightness
                    if commandValues[0].isdigit():
                        try: colorName = ' '.join(commandValues[:3])
                        except Exception as error:
                            print(error, 'commandValues.split()[:3]')
                            request = None
                            continue
                        try: colorBrightness = max(min(int(commandValues[3]), 100), 0)
                        except Exception:
                            print(f'command "{command}" for {bulb.name} failed to return colorBrightness value, defaulting to 35...')
                            colorBrightness = 35
                    else:
                        colorName = commandValues[0]
                        try: colorBrightness = max(min(int(commandValues[1]), 100), 0)
                        except Exception:
                            print(f'command "{command}" for {bulb.name} failed to return colorBrightness value, defaulting to 35...')
                            colorBrightness = 35

                    # limits brightness of bulb right in your face to 65%
                    if not changeAllLights and bulbNumber == 0:
                        max(colorBrightness, 65)

                    # detects custom color names
                    CUSTOM_COLORS = {'examplepurple':'178 0 255',
                                     'examplepurple_altname':'178 0 255',
                                     'withswithcolornamestoo':'red'}
                    if colorName in CUSTOM_COLORS:
                        colorName = CUSTOM_COLORS[colorName]

                    # turn off light(s) and exit (done up here to ensure a smooth transition)
                    if colorName in ('off', 'black', '0 0 0'):
                        print(f'turning {[bulb.name for bulb in self.bulbOrder] if changeAllLights else bulb.name} off, skipping request process...')
                        if changeAllLights: self.sengled_api.set_off(self.bulbOrder)
                        else: self.bulbOrder[bulbNumber].off()
                        request = None
                        continue

                    elif colorName == 'random':   # TODO: do brightness too?
                        colorValue = [randint(0,255), randint(0,255), randint(0,255)]
                        request.random = True


                    # checks if colorName is an RGB value or an actual name and generates a Color object
                    if not colorValue:
                        if colorName[0].isdigit():
                            try: colorObject = Color(rgb=(int(value)/255 for value in colorName.split()))
                            except ValueError as error:
                                print(f'Invalid RGB value requested "{colorName}"\n{error}')
                                continue
                        else:
                            try: colorObject = Color(colorName)
                            except ValueError as error:
                                print(f'Invalid color requested "{colorName}"\n{error}')
                                continue
                        colorValue = [round(value*255) for value in colorObject.rgb]

                    if request is not None:
                        request.id = tags["id"]
                        request.colorValue = colorValue
                        request.colorBrightness = colorBrightness
                        if tags["custom-reward-id"] == "f6932b0f-f218-447e-9158-28677ce90976":      # default
                            request.lightChangingMethod = request.changeLightSimple
                        elif tags["custom-reward-id"] == "cc3f2f61-5960-452a-b22f-57d81b9b7628":    # light fade
                            request.lightChangingMethod = request.changeLightFade

                        self.freeBulbsFromActiveRequests(self.bulbOrder if changeAllLights else [bulb])
                        request.bulbs = self.bulbOrder if changeAllLights else [bulb]
                        pendingRequests.append(request)

            if pendingRequests:
                print(f'\npendingRequests: {pendingRequests}, checking for duplicates')
                self.activeLightRequests = self.mergeBulbRequests(pendingRequests)
                print(f'\nstarting activeLightRequests: {self.activeLightRequests}...')
                for request in self.activeLightRequests:
                    response = request.startRequest()
                    if response < 0:
                        print(f'  {request} returned error code {response}!')


    def mergeBulbRequests(self, requestList=None):
        requests = requestList if requestList else self.activeLightRequests
        dupes = []
        dirtyRequests = []
        for i, request in enumerate(requests):
            toMerge = []
            if request not in dirtyRequests:
                dirtyRequests.append(request)
                for otherRequest in requests[i+1:]:
                    if request == otherRequest:
                        toMerge.append(otherRequest)
                        dirtyRequests.append(otherRequest)
            if toMerge:
                toMerge.append(request)
                dupes.append(toMerge)
        print(f'  duplicate requests to merge (method #3): {dupes}\n')

        mergedRequests = requests
        for mergePair in dupes:
            newRequest = mergePair[0]
            for request in mergePair[1:]:
                newRequest += request
                mergedRequests = [r for r in requests if r is not request]
                request.bulbs = []
            mergedRequests = [r for r in requests if r is not mergePair[0]]
            mergedRequests.append(newRequest)

        mergedRequests = self.clearEmptyRequests(mergedRequests)
        print(f'  new request list:{mergedRequests}\n')
        return mergedRequests


    def clearEmptyRequests(self, requestList=None):
        requests = requestList if requestList else self.activeLightRequests
        print(f'clearing out empty requests from requestList {requestList}...')
        return [request for request in requests if request.bulbs]


    def freeBulbsFromActiveRequests(self, bulbs: list):
        print(f'freeing bulbs {[bulb.name for bulb in bulbs]} from all active requests...')
        for bulb in bulbs:
            for request in self.activeLightRequests:
                print(f'  checking {request} for {bulb.name}')
                if request and request.bulbs:
                    if bulb in request.bulbs:
                        if len(request.bulbs) == 1 and request.hasAliveThread():
                            print(f'   joining {request} thread {request.thread}...')
                            request.thread.join()
                        print(f'   removing {bulb.name} from {request}...')
                        request.bulbs.remove(bulb)
                    else:
                        print(f'   {bulb.name} not in {request}')



class LightRequest:
    def __init__(self, parent, requestID=-1, bulbs=None, lightChangingMethod=None,
                 colorValue=None, colorBrightness=35, colorTemperature=None,
                 delay=0.5, random=False, limitLoops=0):
        self.parent = parent
        self.id = requestID
        self.lightChangingMethod = lightChangingMethod
        self.bulbs = bulbs if bulbs else []
        self.colorValue = colorValue
        self.colorBrightness = colorBrightness
        self.colorTemperature = colorTemperature
        self.delay = delay
        self.random = random
        self._limitLoops = limitLoops
        self._paused = False
        self.thread = None

    def startRequest(self):
        print(f'{self} requesting to start a thread...')
        ###(self.thread is None or not self.thread.is_alive())
        if self.bulbs and not self.hasAliveThread():
            print(f'starting thread with bulbs: {[bulb.name for bulb in self.bulbs]}')
            self.thread = threading.Thread(target=self.lightChangingMethod)
            self.thread.setDaemon(True)
            self.thread.start()
            return 0
        else:
            print('  thread request rejected')
            self.killRequest()

    def killRequest(self):
        print(f'{self} requesting to kill itself...')
        if not self.bulbs:
            self.parent.activeLightRequests = self.parent.clearEmptyRequests()
            return -1
        else:
            print('  kill request rejected, non-empty LightRequest')
            return -2

    def hasAliveThread(self):
        return isinstance(self.thread, threading.Thread) and self.thread.is_alive()

    def __repr__(self):
        return f'LightRequest({[bulb.name for bulb in self.bulbs]})'

    def __eq__(self, other):
        selfAttrs = (self.colorValue, self.colorBrightness, self.colorTemperature, self.delay, self.random)
        otherAttrs = (other.colorValue, other.colorBrightness, other.colorTemperature, other.delay, other.random)
        attrsAreEqual = all(selfAttr == otherAttr for selfAttr, otherAttr in zip(selfAttrs, otherAttrs))
        print(f'__eq__ testing equality between {self} and {other}... {attrsAreEqual}\n  {selfAttrs}\n  {otherAttrs}')
        return attrsAreEqual

    def __add__(self, other):
        print(f'__add__ merging bulbs from {self} and {other}...')
        self.bulbs.extend(other.bulbs)
        print(f'  merged request = {self}')
        return self


    ##############################
    ### light changing methods ###
    ##############################
    def changeLightSimple(self):
        print(f'changeLightSimple...bulbs in this request: {[bulb.name for bulb in self.bulbs]}\n')
        self.parent.sengled_api.set_color(self.bulbs, self.colorValue)
        self.parent.sengled_api.set_brightness(self.bulbs, self.colorBrightness)
        self.parent.sengled_api.set_on(self.bulbs)
        print('changeLightSimple thread CLOSING...')

    def changeLightFade(self):
        print(f'changeLightFade...bulbs in this request: {[bulb.name for bulb in self.bulbs]}\n')
        if not self._limitLoops:
            ###while not _paused:
            while self.bulbs:
                if self.random:
                    self.parent.sengled_api.set_color(self.bulbs, (randint(0,255), randint(0,255), randint(0,255)))
                self.parent.sengled_api.set_brightness(self.bulbs, 50)
                time.sleep(self.delay)
                self.parent.sengled_api.set_brightness(self.bulbs, 0)
                time.sleep(self.delay)
                print(f'self.bulbs for {self} changeLightFade request: {[bulb.name for bulb in self.bulbs]}')
        else:
            _bulbs = self.bulbs.copy()  # copy of bulb list to ensure we can use it
            for _ in range(self._limitLoops):
                if self.random:
                    self.parent.sengled_api.set_color(_bulbs, (randint(0,255), randint(0,255), randint(0,255)))
                self.parent.sengled_api.set_brightness(_bulbs, 100)
                time.sleep(self.delay)
                self.parent.sengled_api.set_brightness(_bulbs, 0)
                time.sleep(self.delay)
            ###self.
        print('changeLightFade thread CLOSING...')
        time.sleep(2)   # forced delay to allow Sengled to catch up





if __name__ == "__main__":
    bot = SengledRewardBot()
    bot.start()