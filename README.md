# Sengled Twitch Client
A Python client for controlling Sengled devices through Twitch alerts and channel rewards.
Designed to be fairly customizable with minimal effort. Includes a config file that can be updated in real-time, as well as 5 premade light effects, ranging from simple static lights to various fading/strobe effects.

You must supply the OAUTH token and Client ID, as well as your Sengled login information. You must also supply the channel reward IDs. In a future update, I'll add an easy way to do this, but for right now, you'll have to modify the on_pubmsg code to print out the "channel-reward-id" key in the "tags" dictionary.

To add a channel reward, open your config file and scroll down to the [REWARDS] section. In here, paste the channel reward ID, then an "=", then the keyword for the light effect you want that reward to use.

Example:
    cc3f2f61-5960-452a-b22f-57d81b9b7629 = fade

Default Keywords:
    static - Simple static light.
    fade - Simple fading light. Fades in, then fades out, on loop.
    fadeonebyone - Like above, but fades each light one by one.
    colorfade - Like fade, but fades into a new color with each loop.
    blink (todo) - Causes lights to blink on and off, on loop.

TODO:
- Add utility for getting channel reward IDs
- Add GUI interface
- Add logging