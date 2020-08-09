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

# TODO: add gui
# TODO: logging
'''
command "red" for Bulb 3 failed to return colorBrightness value, defaulting to 25...
  duplicate requests to merge (method #3): [[None, None]]

  new request list:[LightRequest(?), None]
'''

from irc.bot import SingleServerIRCBot
from irc.schedule import DefaultScheduler
from colour import Color
from random import randint
import sengled
import time, threading
#import requests
import urllib.request, json, hashlib
from configparsebetter import ConfigParseBetter
from light_changing_methods import LIGHT_REWARD_KEYWORDS


class InvalidKeywordError(Exception):
    def __init__(self, keyword):
        self.keyword = keyword
    def __str__(self):
        return f'Keyword "{self.keyword}" not defined'\
                'in light_changing_methods.py'

class ModifierValueMiscountError(Exception):
    def __init__(self, modName, modValues):
        self.modName = modName
        self.modValues = modValues
    def __str__(self):
        return f'Modifier "{self.modName}" with value "{self.modValues}"' \
                'must contain exactly 3 values'

class MissingRewardsError(Exception):
    def __init__(self, file):
        self.file = file
    def __str__(self):
        return 'No rewards have been set under the [REWARDS] section in ' \
              f'{self.file}. Rewards must be set in the following format ' \
               '(without quotes): "reward-id" = "keyword". To bypass this ' \
               'restriction, set "require_rewards_to_start" to False under ' \
               'the [OPTIONS] section.'

class MissingCredentialsError(Exception):
    def __init__(self, cred):
        self.cred = cred
    def __str__(self):
        return f'Required option "{self.cred}" not found. Ensure that all ' \
                'options under the [CREDENTIALS] section are filled out.'

class LoginFailedError(Exception):
    def __str__(self):
        return 'Unable to login to Sengled\'s API. Ensure that all options ' \
               'under the [CREDENTIALS] section are filled out and correct.'


LIGHT_CHANGING_METHODS = {}
CUSTOM_COLORS = {}
MODIFIERS = {
    'dim':      (-96, -96, -96),
    'dark':     (-64, -64, -64),
    'medium':   (-48, -48, -48),
    'deep':     (-32, -32, -32),
    'very':     (-24, -24, -24),
    'pale':     (+96, +96, +96),
    'light':    (+64, +64, +64),
    'baby':     (+48, +48, +48),
    'bright':   (+32, +32, +32),
    'hot':      (1.5, 0.6, 0.9),
    'warm':     (1.25, 0.75, 0.95),
    'cold':     (0.6, 0.9, 1.5),
    'cool':     (0.75, 0.95, 1.25),
    'red':      (+192, 0, 0),
    'green':    (0, +192, 0),
    'blue':     (0, 0, +192),
    'yellow':   (+192, +192, 0),
    'orange':   (+192, +123, 0),
    'gold':     (+192, +161, 0),
    'brown':    (+70, +35, +10),    # based on saddlebrown
    'cyan':     (0, +192, +192),
    'purple':   (+96, 0, +96),
}


def getmd5hash(file='sengledtwitch.ini'):  # 0.085 sec/thousand
    with open(file, 'rb') as file:
        return hashlib.md5(file.read()).hexdigest()


cfg = ConfigParseBetter(filepath='sengled_twitch.ini')
def loadConfig(api=None):
    cfg.read()

    cfg.setSection('CREDENTIALS')
    cfg.load('SENGLED_EMAIL')
    cfg.load('SENGLED_PASS')
    cfg.load('BOT_NAME')
    cfg.load('TARGET_CHANNEL')
    cfg.load('CLIENT_ID')
    cfg.load('OAUTH')
    for option, value in cfg.getItems('CREDENTIALS'):
        if not value:
            raise MissingCredentialsError(option)

    cfg.setSection('OPTIONS')
    cfg.load('REQUEST_COOLDOWN', 15)
    cfg.load('PREFERRED_BULB_ORDER', '')
    cfg.load('CAN_CHANGE_INDIVIDUAL_BULBS', True)
    cfg.load('MODIFIER_ISH_MULTIPLIER', 0.65)
    cfg.load('DEFAULT_DELAY_IN', 1.25)
    cfg.load('DEFAULT_DELAY_OUT', 0.5)
    cfg.load('AUTO_REFRESH_CONFIG', True)
    cfg.load('REQUIRE_REWARDS_TO_START', True)
    cfg.load('REQUEST_CHECK_FREQUENCY', 0.33)
    cfg.load('REQUEST_QUEUE_STATUS_SECONDS', 90)

    cfg.setSection('REWARDS')
    for rID, rKeyword in cfg.loadAllFromSection(returnKey=True):
        if rKeyword not in LIGHT_REWARD_KEYWORDS:
            raise InvalidKeywordError(rKeyword)
        LIGHT_CHANGING_METHODS[rID] = rKeyword
    if cfg.REQUIRE_REWARDS_TO_START and len(cfg.getOptions('REWARDS')) == 0:
        raise MissingRewardsError(cfg.getFilepath())

    cfg.setSection('CUSTOM_COLORS')
    for colorName, colorValue in cfg.loadAllFromSection(returnKey=True):
        colorValue = colorValue.replace(',', ' ')
        while '  ' in colorValue:  # reduces double-spaces to single-spaces
            colorValue = colorValue.replace('  ', ' ')
        CUSTOM_COLORS[colorName] = colorValue

    cfg.setSection('MODIFIERS')
    for modName, modValues in cfg.loadAllFromSection(returnKey=True):
        modValues = modValues.replace(',', ' ')
        while '  ' in modValues:  # reduces double-spaces to single-spaces
            modValues = modValues.replace('  ', ' ')
        modValues = modValues.split()
        if len(modValues) != 3:
            raise ModifierValueMiscountError(modName, modValues)
        MODIFIERS[modName] = modValues.split()

    cfg.setSection('ALERTS')
    cfg.load('ALLOW_FOLLOW_ALERT', True)
    cfg.load('FOLLOW_ALERT_REWARD', 'fade')
    cfg.load('FOLLOW_ALERT_REQUEST', 'red 100 &5')
    cfg.load('ALLOW_SUBSCRIBE_ALERT', True)
    cfg.load('SUBSCRIBE_ALERT_REWARD', 'blink')
    cfg.load('SUBSCRIBE_ALERT_REQUEST', '178 0 255 100 &10')
    cfg.load('ALLOW_BIT_ALERT', True)           # Implementation of various bit
    cfg.load('ALLOW_DONATION_ALERT', True)      # and donation alerts is up to you.

    if api:
        api.bulbOrder = [Bulb(bulb, i) for i, bulb in enumerate(api.preferredBulbOrder)]
        for bulb in api.bulbOrder:
            cfg.setSection('BULB_'+bulb.bulb.name)
            bulb.DEFAULT_BRIGHTNESS = cfg.load('DEFAULT_BRIGHTNESS', 30)
            bulb.MAX_BRIGHTNESS_STATIC = cfg.load('MAX_BRIGHTNESS_STATIC', 66)
            bulb.MIN_BRIGHTNESS_STATIC = cfg.load('MIN_BRIGHTNESS_STATIC', 5)
            bulb.MAX_BRIGHTNESS_DYNAMIC = cfg.load('MAX_BRIGHTNESS_DYNAMIC', 100)
            bulb.MIN_BRIGHTNESS_DYNAMIC = cfg.load('MIN_BRIGHTNESS_DYNAMIC', 0)
            bulb.CAN_TURN_OFF = cfg.load('CAN_TURN_OFF', True)
    print('   Saving config...')
    cfg.write()
    print('   Config saved.')

print('Loading config...')
loadConfig()




class SengledRewardBot(SingleServerIRCBot):
    def __init__(self):
        print('\nInitializing SengledRewardBot...')
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
        #resp = requests.get(url, headers=headers).json()
        request = urllib.request.Request(url=url, headers=headers)
        resp = json.load(urllib.request.urlopen(request))

        self.channel_id = resp["users"][0]["_id"]
        super().__init__([(self.HOST, self.PORT, f"oauth:{self.OAUTH}")], self.BOT_NAME, self.BOT_NAME)

        try:
            print('   Connecting to Sengled API...')
            connectStart = time.time()
            self.sengled_api = sengled.api(username=self.SENGLED_EMAIL, password=self.SENGLED_PASS)
            connectFinish = time.time()
            self.devices = self.sengled_api.get_device_details()
            print(f'      Connected in {connectFinish-connectStart:.2f} seconds.\n')
        except:
            raise LoginFailedError


        if cfg.PREFERRED_BULB_ORDER:
            self.preferredBulbOrder = (self.devices[int(i)] for i in cfg.PREFERRED_BULB_ORDER.split(','))
        else:
            self.preferredBulbOrder = self.devices

        print('   Initializing bulbs...')
        self.bulbOrder = [Bulb(bulb, i) for i, bulb in enumerate(self.preferredBulbOrder)]
        for bulb in self.bulbOrder:
            print(f'      Adding bulb "{bulb.bulb.name}"...')
            cfg.setSection('BULB_'+bulb.bulb.name)
            bulb.DEFAULT_BRIGHTNESS = cfg.load('DEFAULT_BRIGHTNESS', 30)
            bulb.MAX_BRIGHTNESS_STATIC = cfg.load('MAX_BRIGHTNESS_STATIC', 66)
            bulb.MIN_BRIGHTNESS_STATIC = cfg.load('MIN_BRIGHTNESS_STATIC', 5)
            bulb.MAX_BRIGHTNESS_DYNAMIC = cfg.load('MAX_BRIGHTNESS_DYNAMIC', 100)
            bulb.MIN_BRIGHTNESS_DYNAMIC = cfg.load('MIN_BRIGHTNESS_DYNAMIC', 0)
            bulb.CAN_TURN_OFF = cfg.load('CAN_TURN_OFF', True)
        cfg.write()
        self.currentMD5 = getmd5hash(cfg.getFilepath())

        print('   Initializing requestHandlers...')
        self.requestHandlers = [LightRequestHandler(self, i) for i, _ in enumerate(self.bulbOrder)]
        self.requestThreads = [threading.Thread(target=handler.run) for handler in self.requestHandlers]
        for thread in self.requestThreads:
            thread.setDaemon(True)
            thread.start()

        self.queuedLightRequests = []
        self.previousLightRequests = []
        self.startPreviousRequest = False
        self.previousRequestAttempts = 0
        self.lastRequestTime = time.time()
        print('   SengledRewardBot fully initialized, going online...')



    # unused but I didn't delete it because reasons
    def send_message(self, message):
        self.connection.privmsg(self.TARGET_CHANNEL, message)

    # runs when bot starts
    def on_welcome(self, connection, event):
        for req in ("membership", "tags", "commands"):
            connection.cap("REQ", f":twitch.tv/{req}")
        connection.join(self.TARGET_CHANNEL)
        print(f"\nOnline in {self.TARGET_CHANNEL}'s channel. Ready for rewards.")

    # this has something to do with running channel commands (not used)
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

        if user['name'] == 'streamlabs' and message.startswith('Thank you for following'):
            print('\n\n--- FOLLOW DETECTED ---\n\n')
            tags["custom-reward-id"] = cfg.ALERTS.FOLLOW_ALERT_REWARD
            message = cfg.ALERTS.FOLLOW_ALERT_REQUEST

        if "custom-reward-id" in tags and tags["custom-reward-id"] in LIGHT_CHANGING_METHODS:
            print(f'------------------------------\n{user}: {message}')
            rewardID = tags["custom-reward-id"]
            keyword = LIGHT_CHANGING_METHODS[rewardID]
            print(rewardID, keyword)
            print('------------------------------')

            if cfg.AUTO_REFRESH_CONFIG:
                self.refreshConfig()
            self.parseReward(message, keyword)

        elif message[0] == '!':
            command = message[1:]
            if command in ('refreshconfig', 'refreshcfg', 'refreshini',
                               'reloadconfig', 'reloadcfg', 'reloadini',
                               'loadconfig', 'loadcfg', 'loadini',
                               'config', 'cfg', 'ini'):
                self.refreshConfig()
            elif command == 'test':
                self.send_message('PogO')


    def refreshConfig(self):
        newMD5 = getmd5hash(cfg.getFilepath())
        if self.currentMD5 != newMD5:
            print('Refreshing config...')
            loadConfig(self)
            self.currentMD5 = newMD5
            return True
        return False


    def checkForRequests(self):
        # TODO: make into config settings, add exceptions
        checks = 0
        checkDelay = cfg.REQUEST_CHECK_FREQUENCY
        statusRateSeconds = int(cfg.REQUEST_QUEUE_STATUS_SECONDS)
        statusRate = int(statusRateSeconds/cfg.REQUEST_CHECK_FREQUENCY)
        while True:
            checks += 1
            cooldown = cfg.OPTIONS.REQUEST_COOLDOWN
            if checks % statusRate == 0:
                checkDelay = cfg.REQUEST_CHECK_FREQUENCY
                statusRateSeconds = int(cfg.REQUEST_QUEUE_STATUS_SECONDS)
                statusRate = int(statusRateSeconds/checkDelay)
                print(f'{int(cfg.REQUEST_QUEUE_STATUS_SECONDS)}-second Status Update'.center(30,'-'))
                print(f'   Queued rewards ({cooldown} second cooldown): {self.queuedLightRequests}')
                print(f'   Total previous rewards: {len(self.previousLightRequests)}', ''.center(30, '-'))
            if self.queuedLightRequests:
                ignoringCooldown = self.queuedLightRequests[0][2]
                cooldownStatus = "cooldown expired" if ignoringCooldown else "cooldown skipped"
                if ignoringCooldown or self.lastRequestTime + float(cooldown) < time.time():
                    print(f'Queued reward ready and {cooldownStatus}, preparing to start...')
                    nextRequest = self.queuedLightRequests.pop(0)
                    if not self.startPreviousRequest:
                        print('   Starting previous reward...')
                        self.previousLightRequests.append(nextRequest)
                    print(f'   Queued requests remaining: {self.queuedLightRequests}')
                    self.startReward(nextRequest)
            time.sleep(checkDelay)


    def startReward(self, reward):
        pendingRequests, changeAllLights, _ = reward
        print('\nStarting new reward with parameters:')
        print(f'   pendingRequests: {pendingRequests}, changeAllLights: {changeAllLights}')
        if changeAllLights:
            for bulb in self.bulbOrder:
                print('   Setting all bulbs to handlerID 0...')
                bulb.handlerID = 0
            print(f'   Pairing requestHandler #0 with {pendingRequests[0]}...')
            self.requestHandlers[0].request = pendingRequests[0]
        else:
            for bulbNumber, pRequest in enumerate(pendingRequests):
                if pRequest:
                    print(f'   Setting bulb #{bulbNumber}\'s handlerID to {bulbNumber}...')
                    self.bulbOrder[bulbNumber].handlerID = bulbNumber
                    print(f'   Pairing requestHandler #{bulbNumber} with {pRequest}...')
                    self.requestHandlers[bulbNumber].request = pRequest
        self.lastRequestTime = time.time()


    def parseReward(self, message, keyword, ignoreCooldown=False):
        commands = message.lower().split(';')[:len(self.bulbOrder)]
        if not cfg.OPTIONS.CAN_CHANGE_INDIVIDUAL_BULBS:
            commands = commands[:1]
        changeAllLights = True if len(commands) == 1 else False

        pendingRequests = []
        self.startPreviousRequest = False

        for (bulb, command) in zip(self.bulbOrder, commands):
            pendingRequests.append(None)
            if command:
                random = False
                limitLoops = 0
                colorValue = None
                colorValues = []
                multiColorValue = []
                colorBrightness = None
                commandValues = None
                turnOff = False
                delays = []
                useColorRange = False
                colorRange = 0
                colorObjects = []


                # cuts out unneeded characters for more lenient formatting
                for extraneousCharacter in ('`~!@$%^*()_=+[{]}\\|;:\'"</?'):
                    command = command.replace(extraneousCharacter, '')
                #command = command.replace('.', ' ')
                command = command.replace(',', ' ')
                command = command.replace(' -> ', '->')

                potentialColors = command.split('->')
                for pColor in potentialColors:
                    pColor = pColor.strip()
                    while '  ' in pColor:  # reduces double-spaces to single-spaces
                        pColor = pColor.replace('  ', ' ')
                    while '& ' in pColor:   # TODO necessary?
                        pColor = pColor.replace('& ', '&')
                    if pColor[0].isdigit():    # starts with number -> assume RGB and remove letters
                        for alphaCharacter in ('abcdefghijklmnopqrstuvwxyz'):
                            pColor = pColor.replace(alphaCharacter, '')
                        pColorValues = pColor.split()
                        pColor = ' '.join(pColorValues[:3])
                        if len(pColorValues) < 3:
                            continue
                        elif len(pColorValues) > 3:
                            commandValues = pColorValues[3:]

                    elif pColor[0].isalpha():  # TODO better way to do this?
                        pColor = pColor.replace(' ', '')
                        pColor = pColor.replace('&', ' &')
                        for i, c in enumerate(pColor):
                            if c.isdigit():
                                pColor = pColor[:i]
                                commandValues = pColor[i:]
                                break
                    colorValues.append(pColor)
                    if commandValues:
                        break
                if not commandValues:
                    commandValues = potentialColors[-1].split()[1:]


                addingDelays = False
                for value in commandValues:
                    if value[0] == 'b':
                        try: colorBrightness = int(value[1:])
                        except: print(f'Brightness "{value}" failed to return value...')
                        addingDelays = False
                    elif value[-1] == '%':
                        try: colorBrightness = int(value[:-1])
                        except: print(f'Brightness "{value}" failed to return value...')
                        addingDelays = False
                    elif value[0] == '&':
                        try: limitLoops = int(commandValue[1:])
                        except: print(f'Limit loops "{value}" failed to return value...')
                        addingDelays = False
                    elif value[0] == 'r':
                        try:
                            colorRange = int(value[1:])
                            if colorRange > 2 and len(colorValues) > 1:
                                useColorRange = True
                        except: print(f'range_to "{value}" failed to return value...')
                    elif value[0] == 'd':
                        try: delays.append(float(value[1:]))
                        except: print(f'Delay "{value}" failed to return value...')
                        addingDelays = True
                    elif addingDelays:
                        try: delays.append(float(value))
                        except: print(f'Added delay "{value}" failed to return value...')
                    elif not colorBrightness:
                        colorBrightness = value

                try:
                    colorBrightness = max(min(int(commandValues[0]), 100), 0)
                except Exception:
                    print(f'command "{command}" for {bulb.bulb.name} failed to return colorBrightness value, defaulting to 25...')
                    colorBrightness = bulb.DEFAULT_BRIGHTNESS

                # limits brightnesses to each bulb's bounds
                if changeAllLights:
                    for b in self.bulbOrder:
                        max(colorBrightness, b.MAX_BRIGHTNESS_STATIC)
                        min(colorBrightness, b.MIN_BRIGHTNESS_STATIC)
                else:
                    max(colorBrightness, bulb.MAX_BRIGHTNESS_STATIC)
                    min(colorBrightness, bulb.MIN_BRIGHTNESS_STATIC)


                if colorValues[0] in ('last','previous','redo','restore','undo'):
                    self.startPreviousRequest = True
                    self.previousRequestAttempts += 1
                    prevIndex = -1 - self.previousRequestAttempts
                    try: self.queuedLightRequests.append(self.previousLightRequests[prevIndex])
                    except: pass
                    return
                else:
                    self.previousRequestAttempts = 0


                if colorValues[0] == 'rainbow':
                    colorValues = (     # ROYGBIV
                        '255 0 0',      # red
                        '255 150 0',    # orange
                        '255 255 0',    # yellow
                        '0 255 0',      # green
                        '0 0 255',      # blue
                        '46 43 95',     # indigo
                        '139 0 255',    # purple
                    )


                for i, colorName in enumerate(colorValues):
                    print(i, colorName, self.bulbOrder)
                    # detects custom color names
                    if colorName in CUSTOM_COLORS:
                        colorName = CUSTOM_COLORS[colorName]

                    # turn off light(s) and exit (done up here to ensure a smooth transition)
                    elif colorName in ('off', 'black', '0 0 0'):
                        turnOff = True
                        #self.queuedLightRequests.append()
                        #if not changeAllLights:
                        #    bulb.off()
                        #else:
                        #    for b in self.bulbOrder:
                        #        b.off()
                        #continue

                    elif colorName == 'random':
                        colorName = f'{randint(0,255)} {randint(0,255)} {randint(0,255)}'
                        random = True

                    # checks if colorName is an RGB value or an actual name and generates a Color object
                    if not turnOff:
                        colorObject = None
                        if colorName[0].isdigit():
                            try: colorObject = Color(rgb=(int(value)/255 for value in colorName.split()))
                            except ValueError as error:
                                print(f'Invalid RGB value requested "{colorName}"\n{error}')
                                continue    # TODO this and other one -> cfg.default_color?
                        else:
                            try: colorObject = Color(colorName)
                            except ValueError as error:
                                print(f'(!) Invalid color name requested "{colorName}"\n{error}')
                                print('    Checking for modifiers...')
                                for modName, modValues in MODIFIERS.items():
                                    ish = cfg.OPTIONS.MODIFIER_ISH_MULTIPLIER
                                    if colorName.startswith(modName+'ish'):
                                        print(1, colorName, modName, modValues)
                                        newModValues = [int(v*ish) if isinstance(v, int) else v*ish for v in modValues]
                                        colorObject = self.addColorModifier(colorName.replace(modName+'ish', ''), modName, newModValues)
                                    elif colorName.startswith(modName+'-ish'):
                                        print(2, colorName, modName, modValues)
                                        newModValues = [int(v*ish) if isinstance(v, int) else v*ish for v in modValues]
                                        colorObject = self.addColorModifier(colorName.replace(modName+'-ish', ''), modName, newModValues)
                                    elif colorName.startswith(modName[:-1]+'ish'):
                                        newModValues = [int(v*ish) if isinstance(v, int) else v*ish for v in modValues]
                                        colorObject = self.addColorModifier(colorName.replace(modName[:-1]+'ish', ''), modName, newModValues)
                                    elif colorName.startswith(modName[:-1]+'-ish'):
                                        newModValues = [int(v*ish) if isinstance(v, int) else v*ish for v in modValues]
                                        colorObject = self.addColorModifier(colorName.replace(modName[:-1]+'-ish', ''), modName, newModValues)
                                    elif colorName.startswith(modName):
                                        print(3, colorName, modName, modValues)
                                        colorObject = self.addColorModifier(colorName, modName, modValues)

                                if colorObject is None:
                                    continue
                        print('u suck lemons', colorObject)
                        if colorObject:
                            colorObjects.append(colorObject)

                        if not useColorRange:
                            print('u DONT suck lmeons hehehehh', colorObject, [round(value*255) for value in colorObject.rgb], (round(value*255) for value in colorObject.rgb), tuple(round(value*255) for value in colorObject.rgb))
                            multiColorValue.append(tuple(round(value*255) for value in colorObject.rgb))
                        else:
                            if i == 0: continue
                            for rangedColor in colorObjects[i-1].range_to(colorObjects[i], colorRange):
                                multiColorValue.append(tuple(round(value*255) for value in rangedColor.rgb))
                del colorObjects

                print(7,multiColorValue, colorValue, colorValues, self.bulbOrder)
                if len(multiColorValue) > 1 and keyword == 'fade':
                    keyword = 'colorfade'   # TODO make this adapt to config somehow?
                    colorValue = None
                else:
                    colorValue = multiColorValue[0]
                    multiColorValue = None
                if not delays:  # TODO this doesn't return a float on its own
                    delays.append(float(cfg.OPTIONS.DEFAULT_DELAY_IN))
                    delays.append(float(cfg.OPTIONS.DEFAULT_DELAY_OUT))

                print('Creating request...', multiColorValue, colorValue)
                request = LightRequest(
                    parent=self,
                    lightChangingMethod=LIGHT_REWARD_KEYWORDS[keyword],
                    colorValue=colorValue,
                    multiColorValue=multiColorValue,
                    colorBrightness=colorBrightness,
                    delays=delays,
                    random=random,
                    limitLoops=limitLoops,
                    turnOff=turnOff
                )

                pendingRequests[-1] = request
                self.freeBulbsFromActiveRequests(self.bulbOrder if changeAllLights else [bulb])
                if changeAllLights:
                    break

        if pendingRequests:
            if not changeAllLights:
                pendingRequests = self.mergeLightRequests(pendingRequests)
            self.queuedLightRequests.append((pendingRequests, changeAllLights, ignoreCooldown))
            print('Reward has been queued.', self.bulbOrder, [b.id for b in self.bulbOrder],[b.handlerID for b in self.bulbOrder], pendingRequests, pendingRequests[0].colorValue,pendingRequests[0].colorBrightness,)


    def mergeLightRequests(self, requests):
        print('   Checking for duplicate requests to merge...')
        dupes = []
        dirtyRequests = []
        for i, request in enumerate(requests):
            toMerge = []
            if request not in dirtyRequests:
                dirtyRequests.append(request)
                for otherRequest in requests[i+1:]:
                    if request and request == otherRequest:
                        toMerge.append(otherRequest)
                        dirtyRequests.append(otherRequest)
            if toMerge:
                toMerge.append(request)
                dupes.append(toMerge)
        print(f'      Duplicate requests to merge (method #3): {dupes}\n')

        mergedRequests = requests
        for mergePair in dupes:
            newRequest = mergePair[0]
            for request in mergePair[1:]:
                if newRequest and request:
                    newRequest += request
                    mergedRequests = [r for r in requests if r is not request]
                    request.bulb = []
            mergedRequests = [r for r in requests if r is not mergePair[0]]
            mergedRequests.append(newRequest)

        print(f'      New request list:{mergedRequests}\n')
        return mergedRequests


    def freeBulbsFromActiveRequests(self, bulbs):
        print(f'   Freeing bulbs {bulbs} by setting their handlerIDs to -1...')
        for bulb in bulbs:
            bulb.handlerID = -1


    def addColorModifier(self, colorName, modName, modValues):
        print(f'    Modifier "{modName}" detected, attempting to add modValues {modValues} to colorName {colorName}')
        colorName = colorName.replace(modName, '', 1)
        try:
            colorObject = Color(colorName)
            newValues = []
            for oldValue, newValue in zip(colorObject.rgb, modValues):
                # TODO: max(0, <- CAUSES STROBE EFFECT!!! REMEMBER THIS
                if isinstance(newValue, int):
                    print(10)
                    newValues.append(max(0.05, min(1, ((oldValue*255)+newValue)/255)))
                elif isinstance(newValue, float):
                    print(20)
                    newValues.append(max(0.05, min(1, oldValue*newValue)))
            print(colorObject.rgb, newValues)
            colorObject.rgb = newValues
            return colorObject
        except ValueError as error:
            print(f'    Color is still invalid, giving up. Non-fatal error: "{error}"')
            return None



class LightRequest:
    def __init__(self, parent, lightChangingMethod=None,
                 colorValue=None, multiColorValue=None,
                 colorBrightness=25, delays=None,
                 random=False, limitLoops=0, turnOff=False):
        self.parent = parent
        self.running = True         # TODO this does nothing right now
        self.waiting = False
        self.waitForSync = False
        self.lightChangingMethod = lightChangingMethod
        self.colorValue = colorValue
        self.multiColorValue = multiColorValue
        self.colorBrightness = colorBrightness
        self.delays = delays
        self.random = random
        self._limitLoops = limitLoops
        self._loops = 0
        self._yields = 0
        self.turnOff = turnOff

    def __repr__(self):
        return f'LightRequest({self.colorValue})'

    def __eq__(self, other):
        if isinstance(other, LightRequest):
            selfAttrs = (
                self.colorValue,
                self.colorBrightness,
                self.lightChangingMethod,
                self.delays,
                self.random,
                self._limitLoops
            )
            otherAttrs = (
                other.colorValue,
                other.colorBrightness,
                other.lightChangingMethod,
                other.delays,
                other.random,
                other._limitLoops
            )
            attrsAreEqual = all(selfAttr == otherAttr for selfAttr, otherAttr in zip(selfAttrs, otherAttrs))
            print(f'      __eq__ testing equality between {self} and {other}... {attrsAreEqual}')
            print(f'         {selfAttrs}\n         {otherAttrs}')
            return attrsAreEqual
        return False

    @property
    def handler(self):
        for handler in self.parent.requestHandlers:
            if handler.request and handler.request == self:
                return handler
        return None

    def __add__(self, other):
        # TODO could this be in LightRequestHandler instead?
        print(f'      __add__ merging bulbs from {self} and {other}...')
        for bulb in self.parent.bulbOrder:
            if other.handler and other.handler.id == bulb.handlerID:
                bulb.handlerID = self.handler.id
        other.request = None
        return self



class Bulb:
    def __init__(self, bulb, _id):
        self.bulb = bulb
        self.id = _id
        self.handlerID = -1
        self.DEFAULT_BRIGHTNESS = 30
        self.MAX_BRIGHTNESS_STATIC = 66
        self.MIN_BRIGHTNESS_STATIC = 5
        self.MAX_BRIGHTNESS_DYNAMIC = 100
        self.MIN_BRIGHTNESS_DYNAMIC = 0
        self.CAN_TURN_OFF = True

    def off(self):
        print(f'   Turning bulb {self.bulb.name} off...')
        if self.CAN_TURN_OFF:
            print('      Setting handlerID to -1...')
            self.handlerID = -1
            print('      Setting brightness to 0...')
            self.bulb.set_brightness(0)
            print('      Setting bulb to off...')
            self.bulb.off()
            print(f'      Request to turn bulb {self.bulb.name} off completed.')
        else:
            print(f'      Request to turn bulb {self.bulb.name} off rejected by config.')

    def __call__(self):
        return self.bulb



class LightRequestHandler:
    def __init__(self, parent, _id, request=None):
        self.parent = parent
        self.id = _id
        self.request = request

    def refreshBulbs(self):
        return [bulb.bulb for bulb in self.parent.bulbOrder if bulb.handlerID == self.id]

    def allRequestsAreWaiting(self):
        return all(not h.request or h.request.waiting for h in self.parent.requestHandlers)

    def run(self):
        print(f"      Starting LightRequestHandler #{self.id}...")
        while True:
            try:
                if self.request and (not self.request.waitForSync or self.allRequestsAreWaiting()):
                    bulbs = self.refreshBulbs()
                    if self.request.turnOff:
                        bulbNames = list(b.name for b in bulbs)
                        print(f'Request for turnOff received, turning off bulbs {bulbNames}...')
                        for bulb in bulbs:
                            bulb.off()
                    if bulbs:
                        for _ in self.request.lightChangingMethod(self.request, bulbs):
                            self.request._yields += 1
                            self.request.waiting = self.request.waitForSync
                            bulbs = self.refreshBulbs()
                            if not self.request.running or not bulbs:
                                print(500)
                                break
                        self.request._loops += 1
                    else:
                        print(f'{self} no longer has bulbs, suspending...')
                        self.request = None
            except Exception as error:
                print(f"(!) {self} error: {error}")
            time.sleep(0.2)

    def __repr__(self):
        return f"LightRequestHandler #{self.id} (request: {self.request})"





if __name__ == "__main__":
    bot = SengledRewardBot()
    requestChecker = threading.Thread(target=bot.checkForRequests)
    requestChecker.start()
    bot.start()
    print('Closing...')
    cfg.write()