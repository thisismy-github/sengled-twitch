'''
INSTRUCTIONS:
to be added
    self.parent
    self.running
    self.waiting                (bool -> request is actively waiting to continue)
    self.waitForSync            (bool -> request waits to continue after yield)
    self.lightChangingMethod
    self.colorValue
    self.colorBrightness
    self.delay
    self.random
    self._limitLoops
    self._loops
'''

import random, time

##########################################################
#############     LIGHT CHANGING METHODS     #############
##########################################################
def changeLightSimple(self, bulbs):
    self.waitForSync = False
    self.parent.sengled_api.set_color(bulbs, self.colorValue)
    self.parent.sengled_api.set_brightness(bulbs, self.colorBrightness)
    self.parent.sengled_api.set_on(bulbs)
    yield



def changeLightFade(self, bulbs):
    print('NOT HERE!!!!!!! FADECOLOR BABY!!!!')
    self.waitForSync = True
    if self.random:
        self.parent.sengled_api.set_color(bulbs, (random.randint(0,255),
                                                  random.randint(0,255),
                                                  random.randint(0,255)))
    elif self._loops == 0:
        self.parent.sengled_api.set_color(bulbs, self.colorValue)


    if not self._limitLoops or (self._limitLoops and self._loops <= self._limitLoops):
        # 1&2 -> one light at a time | 1 -> synced, but mixed
        #self.waiting = False
        #self._loops += 1
        print(self.delays)
        self.parent.sengled_api.set_brightness(bulbs, self.colorBrightness)
        yield
        time.sleep(self.delays[self._yields%len(self.delays)])
        self.waiting = False
        self.parent.sengled_api.set_brightness(bulbs, 0)
        yield
        time.sleep(self.delays[self._yields%len(self.delays)])
    elif self._limitLoops and self._loops > self._limitLoops:
        self.parent.parseReward('last', None, ignoreCooldown=True)



def changeLightFadeOneByOne(self, bulbs):
    self.waitForSync = True
    if self.random:
        self.parent.sengled_api.set_color(bulbs, (random.randint(0,255),
                                                  random.randint(0,255),
                                                  random.randint(0,255)))
    elif self._loops == 0:
        self.parent.sengled_api.set_color(bulbs, self.colorValue)

    if not self._limitLoops or (self._limitLoops and self._loops <= self._limitLoops):
        # 1&2 -> one light at a time | 1 -> synced, but mixed
        self.waiting = False
        #self._loops += 1

        self.parent.sengled_api.set_brightness(bulbs, self.colorBrightness)
        yield
        self.waiting = False
        self.parent.sengled_api.set_brightness(bulbs, 0)
        yield
    elif self._limitLoops and self._loops > self._limitLoops:
        self.parent.parseReward('last', None, ignoreCooldown=True)



def changeLightFadeColor(self, bulbs):
    print('HERE!!!!!!! FADECOLOR BABY!!!!')
    self.waitForSync = True
    print(1)
    if self._loops == 0:
        print(2, self.multiColorValue[0])
        self.parent.sengled_api.set_color(bulbs, self.multiColorValue[0])

    print(self._limitLoops, self._loops)
    if not self._limitLoops or (self._limitLoops and self._loops <= self._limitLoops):
        print('bad')
        nextColor = [self.multiColorValue[self._loops%len(self.multiColorValue)]]
        print(nextColor)
        self.parent.sengled_api.set_color(bulbs, nextColor)
        # 1&2 -> one light at a time | 1 -> synced, but mixed
        #self.waiting = False
        #self._loops += 1

        self.parent.sengled_api.set_brightness(bulbs, self.colorBrightness)
        yield
        time.sleep(self.delays[self._yields%len(self.delays)])
        self.waiting = False
        self.parent.sengled_api.set_brightness(bulbs, 0)
        yield
        time.sleep(self.delays[self._yields%len(self.delays)])
    elif self._limitLoops and self._loops > self._limitLoops:
        self.parent.parseReward('last', None, ignoreCooldown=True)



def changeLightBlink(self, bulbs):
    pass


##########################################################
####################     KEYWORDS     ####################
##########################################################
LIGHT_REWARD_KEYWORDS = {
    "static": changeLightSimple,
    "fade": changeLightFade,
    "fadeonebyone": changeLightFadeOneByOne,
    "colorfade": changeLightFadeColor,
    "blink": changeLightBlink,
}