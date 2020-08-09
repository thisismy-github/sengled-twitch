# TODO: .load() -> 5.6 sec/million

import configparser, sys

class LockedNameException(Exception):
    def __init__(self, name):
        self.name = name
    def __str__(self):
        return f'Option name "{self.name}" is not allowed ' \
                '(___parser, ___section, ___filepath, ' \
                '___sectionLock, ___defaultExtension).'

class SetSectionToValueError(Exception):
    def __init__(self, name):
        self.name = name
    def __str__(self):
        return f'Setting a section ("{self.name}") to a value is not allowed.'

class InvalidSectionError(Exception):
    def __init__(self, name, caller):
        self.name = name
        self.caller = caller
    def __str__(self):
        return f'{self.caller}: "{self.name}" is not a valid section.'



class ConfigParseBetter:
    ___sectionLock = False
    ___defaultExtension = '.ini'    # unused

    def __init__(self, ConfigParserObject=None, filepath=None):
        # Using objects as default values will always init them first.
        if ConfigParserObject is None:
            self.___parser = configparser.ConfigParser()
        else:
            self.___parser = ConfigParserObject
        self.___section = 'DEFAULT'

        self.___filepath = filepath
        if not filepath:
            if sys.argv[0]:
                self.___filepath = sys.argv[0].split('\\')[-1][:-3]
            else:
                self.___filepath = 'config'
        if self.___filepath[-4:] not in ('.ini', '.cfg'):
            self.___filepath += self.___defaultExtension
        self.read(self.___filepath)

    def read(self, filepath=None):
        filepath = filepath if filepath else self.___filepath
        self.___parser.read(filepath)

    def write(self, filepath=None):
        filepath = filepath if filepath else self.___filepath
        with open(filepath, 'w') as configfile:
            self.___parser.write(configfile)

    def read_dict(self, dictionary, *args, **kwargs):
        self.___parser.read_dict(dictionary, *args, **kwargs)

    def read_file(self, file, *args, **kwargs):
        self.___parser.read_file(file, *args, **kwargs)

    def read_string(self, string, *args, **kwargs):
        self.___parser.read_string(string, *args, **kwargs)

    def load(self, key, fallback='', section=None):
        section, value = self._load(key, fallback, section)
        section[key] = str(value)   # 1.0595 sec/million
        self.__dict__[key] = value  # 0.1276 sec/million
        return value

    def loadFrom(self, section, key, fallback=''):
        return self._load(key, fallback, section)

    def loadAllFromSection(self, section=None, fallback='',
                           name=None, returnKey=False):
        # TODO: If load() is called before setSection(), this will start
        #       returning the settings loaded without a section, even
        #       though they should be loaded into the 'DEFAULT' section.
        section = self.getSection(section)
        if name:
            for sectionKey in self.___parser.options(section.name):
                if sectionKey.startswith(name):
                    if returnKey:
                        yield sectionKey, self.load(sectionKey, fallback, section)
                    else:
                        yield self.load(sectionKey, fallback, section)
        else:
            for sectionKey in self.___parser.options(section.name):
                if returnKey:
                    yield sectionKey, self.load(sectionKey, fallback, section)
                else:
                    yield self.load(sectionKey, fallback, section)

    def _load(self, key, fallback, section=None, verifySection=True):
        if key[:2] == '__':
            raise LockedNameException(key)
        if verifySection:
            section = self.getSection(section)
        if section.name in self.___parser.sections():
            try:
                if type(fallback) == bool:
                    return section, section.getboolean(key, fallback=fallback)
                elif type(fallback) == int:
                    return section, section.getint(key, fallback=fallback)
                elif type(fallback) == float:
                    return section, section.getfloat(key, fallback=fallback)
                return section, section.get(key, fallback=fallback)
            except:
                return section, fallback
        elif not self.___sectionLock:
            return section, self._loadFromAnywhere(key, fallback)
        else:
            return section, fallback    # add elif for raising error here?

    def _loadFromAnywhere(self, key, fallback):
        for section in self.___parser.sections():
            for sectionKey in self.___parser.options(section):
                if sectionKey == key.lower():
                    return self.___parser[section][sectionKey]
        return fallback

    def save(self, key, *values, delimiter=','):
        section = self.getSection()
        section[key] = delimiter.join(str(value) for value in values)

    def saveToSection(self, section, key, *values, delimiter=','):
        section[key] = delimiter.join(str(value) for value in values)

    def sections(self, name=None):
        if name: self.___sectionsByName(name)
        else: return self.___parser.sections()

    def ___sectionsByName(self, name):
        for section in self.___parser.sections():
            if section.startswith(name):
                yield section

    def setSection(self, section):
        self.___section = self.getSection(section)

    def getSection(self, section=None): # could this be faster?
        # TODO test try/except vs if statements for checking for sections
        if section is None:
            if self.___section is None:
                try:
                    section = self.___parser['DEFAULT']
                except:
                    self.___parser['DEFAULT'] = {}
                    section = self.___parser['DEFAULT']
            else:
                section = self.___section

        if isinstance(section, configparser.SectionProxy):
            try:
                return section
            except KeyError:
                name = section.name
                section = {}
                self.__dict__[name] = BetterSectionProxy(self, name)
                return section
        else:
            try:
                return self.___parser[section]
            except KeyError:
                self.___parser[section] = {}
                self.__dict__[section] = BetterSectionProxy(self, section)
                return self.___parser[section]

    def getParser(self):
        return self.___parser

    def getFilepath(self):
        return self.___filepath

    def getOptions(self, section):
        try:
            section = section if type(section) == str else section.name
            return self.___parser.options(section)
        except:
            raise InvalidSectionError(section, 'getOptions')

    def getItems(self, section):
        try:
            section = section if type(section) == str else section.name
            return self.___parser.items(section)
        except:
            raise InvalidSectionError(section, 'getItems')

    def getValues(self, section):
        try:
            section = section if type(section) == str else section.name
            return self.___parser.values(section)
        except:
            raise InvalidSectionError(section, 'getValues')

    def __getitem__(self, key):
        try: return self.___parser[key]
        except: return None

    def __setitem__(self, key, val):
        self.___parser[key] = val

    def __getattr__(self, name):
        if name in self.sections():
            return BetterSectionProxy(self, name)
        return self._loadFromAnywhere(key=name, fallback=None)



class BetterSectionProxy:
    def __init__(self, parent, section):
        self.___parent = parent
        self.___section = self.___parent.getParser()[section]
    def __getattr__(self, name):
        return self.___section[name]
    def __setattr__(self, name, val):
        self.__dict__[name] = val
        if name[:19] != '_BetterSectionProxy':
            self.___section[name] = str(val)
            self.___parent.__dict__[name] = val