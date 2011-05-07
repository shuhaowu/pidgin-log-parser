# -*- coding: utf-8 -*-
from BeautifulSoup import BeautifulSoup, NavigableString
import sys, os, re, time
import cPickle
from bisect import bisect_left

SHOWMATCHED = 0

def inList(l, x):
    i = bisect_left(l, x)
    return i != len(l) and l[i] == x

def show(message):
    if SHOWMATCHED:
        print >> sys.stderr, message

def save(obj, filename):
    f = open(filename, "w")
    cPickle.dump(obj, f)
    f.close()

def load(filename):
    f = open(filename)
    sessions = cPickle.load(f)
    f.close()
    return sessions

def stringlistToLower(l):
    if l:
        for i in xrange(len(l)):
            l[i] = l[i].lower()
    return l


class ParserWarning:
    def __init__(self, message, problem, severity=1, **details):
        self.message = str(message)
        self.problem = problem
        self.severity = severity
        self.details = details

    def __str__(self):
        text = "\nWarning (%d): %s\nProblem: %s" % (self.severity, self.message, str(self.problem))
        if len(self.details):
            text += "\nAdditional Details"
            for key in self.details:
                text += "\n  %s: %s" % (key, self.details[key])
        text += "\n"
        return text

    def __repr__(self):
        return "<Warning (%d): %s>" % (self.severity, self.message)

class Message:
    def __init__(self, date, t, sender, message):
        self.time = "%s %s" % (date, t)
        self.struct_time = time.strptime(self.time, "%m/%d/%Y %I:%M:%S %p")
        self.timestamp = time.mktime(self.struct_time)
        self.sender = sender
        self.message = message

    def __repr__(self):
        return "<%s: %s>" % (self.sender, self.message)

    def __str__(self):
        return "%s (%s): %s" % (self.sender, self.time, self.message)


class ChatSession:
    def __init__(self, contact, date):
        self.contact = contact
        self.date = date
        self.messages = []
        self.nicks = {}

    def addMessage(self, time, sender, message):
        self.messages.append(Message(self.date, time, sender, message))
        i = self.nicks.get(sender, 0)
        i += 1
        self.nicks[sender] = i

    def sort(self):
        self.messages.sort(key=lambda m: m.timestamp)

    def __repr__(self):
        return "<Conversation with %s on %s>" % (self.contact, self.date)
        
        

class PidginLogParser:
    def __init__(self, directory):
        self.warnings = []
        self.titleRegexPattern = re.compile("^Conversation with (.+) at (.+?) .+$")

        self.sessions = AllChatSessions()

        for filename in os.listdir(directory):
            if filename.endswith(".html"):
                self.sessions.append(self.parseLog(os.path.join(directory, filename)))

        self.sessions.constructBasicInfo()
        print "Parsing Complete. Warning count: %d" % len(self.warnings)
        

    def parseLog(self, logfile):
        rawlog = self.getLog(logfile)
        soup = self.getSoupFromLog(rawlog)
        contact, date = self.getCoreInfo(soup)
        
        session = ChatSession(contact, date)
        chats = soup.findAll(attrs={"class":"chat"})
        for tag in chats:
            t, sender, message = self.getChat(tag)
            if message == None:
                continue
            session.addMessage(t, sender, message)
        session.sort()
        return session
            
    def getLog(self, logfile):
        with open(logfile) as f:
            rawlog = f.read()
        return rawlog

    def getSoupFromLog(self, rawlog):
        rawlog = rawlog.split("\n")
        for i in xrange(len(rawlog)):
            rawlog[i] = rawlog[i].replace("<br/>", "")
            if rawlog[i].startswith("<font color"):
                rawlog[i] = "<p class=\"chat\">" + rawlog[i] + "</p>"
        rawlog = "\n".join(rawlog)
        return BeautifulSoup(rawlog, convertEntities=BeautifulSoup.HTML_ENTITIES)

    def warning(self, message, problem, severity=1, **details):
        w = ParserWarning(message, problem, severity, **details)
        self.warnings.append(w)
        print >> sys.stderr, str(w)
    

    def save(self, filename):
        self.sessions.save(filename)

    def savewarnings(self, filename):
        save(self.warnings, filename)

    def recursiveFindString(self, tag):
        if type(tag) == unicode:
            return tag
        
        if len(tag.contents) > 1:
            self.warning("Tag Content Length is above 1. Disregarding non 0th element.", repr(tag.contents), severity=2, Length=len(tag.contents), Tag=repr(tag))
        elif len(tag.contents) <= 0:
            self.warning("Tag Content Length is 0.", repr(tag), Content=repr(tag.contents), Length=len(tag.contents))
            return None
        if type(tag.contents[0]) != NavigableString:
            return self.recursiveFindString(tag.contents[0])
        else:
            return unicode(tag.contents[0])
        
    @staticmethod
    def stripLinks(tag):
        i = 0
        stringTypes = (unicode, NavigableString)
        while i < len(tag.contents):
            if type(tag.contents[i]) not in stringTypes:
                if tag.contents[i].name == "a":
                    tag.contents[i].replaceWith(tag.contents[i].renderContents())

            i += 1
            if i == 0:
                continue
            if i >= len(tag.contents):
                break
            if type(tag.contents[i]) in stringTypes and type(tag.contents[i-1]) in stringTypes:
                tag.contents[i-1] = "".join((tag.contents[i-1], tag.contents[i]))
                del tag.contents[i]
                
                i -= 1
            
            
        

    def getChat(self, chatTag):
        time = chatTag.findAll("font", attrs={"size":"2"})[0].contents[0]
        time = time.strip("()")

        speaker = chatTag.findAll("b")[0].contents[0].strip().strip(":")

        

        chat = None
        i = 0
        while len(chatTag.contents) > 3:
            print >> sys.stderr, "Notice: Stripping Links from %s\n" % repr(chatTag)
            self.stripLinks(chatTag)
            i += 1
            if i >= 10:
                self.warning("Cannot reduce content length to 3.", chatTag, severity=3)
                break

        length = len(chatTag.contents)
        
        if length == 2:
            chat = chatTag.contents[1]
            if chat.__class__.__name__ == "NavigableString":
                chat = unicode(chat)
            elif chat.__class__.__name__ == "Tag":
                chat = self.recursiveFindString(chat)
            else:
                self.warning("Mismatch Message Type", chat, Type=chat.__class__.__name__)
        elif length == 3:
            chat = chatTag.contents[2]
            chat = self.recursiveFindString(chat)
        else:
            self.warning("Message Length Mismatch", chatTag, Length=length)
            
        return time, speaker, self.cleanupMessage(chat)

    def cleanupMessage(self, message):
        if message == None:
            return None
        message = message.strip()
        message = message.replace("&apos;", "'")
        return message
        
    def getCoreInfo(self, soup):
        title = str(soup.findAll("title")[0].contents[0])
        m = self.titleRegexPattern.match(title)
        return unicode(m.group(1)), unicode(m.group(2))

    

class AllChatSessions(list):
    def __init__(self, *args, **kwargs):
        super(list, self).__init__(*args, **kwargs)
        self.nicks = {}
        self.dates = []

    def save(self, filename):
        save(self, filename)

    def append(self, x):
        if x.__class__ == ChatSession:
            list.append(self, x)
            for key in x.nicks:
                temp = self.nicks.get(key, 0)
                temp += x.nicks[key]
                self.nicks[key] = temp
                
            self.dates.append(x.date)
        else:
            raise TypeError("Must be a ChatSession instance.")

    def constructBasicInfo(self):
        for key in self.nicks:
            temp = self.nicks[key]
            self.nicks[key] = {
                              "messages" : temp,
                              "words" : self.wordcount([key]),
                              "characters" : self.charactercount([key])
                              }
            

    def dataCount(self, callback, senders=[], showMatched=False):
        senders = stringlistToLower(senders)
        count = 0
        for session in self:
            for message in session.messages:
                if self.checkSender(message, senders):
                    add = callback(message, senders)
                    #print message, senders, add
                    if add and (showMatched or SHOWMATCHED):
                        show("%s (%s): %s" % (message.sender, message.time, message.message))
                    count += add
                    
        return count

    @staticmethod
    def checkSender(message, senders):
        return (not senders) or (senders and (message.sender.lower() in senders))

    def wordcount(self, senders=[], showMatched=False):
        def wc(message, senders):
            return len(message.message.split())

        return self.dataCount(wc, senders, showMatched)

    def charactercount(self, senders=[], showMatched=False):
        def cc(message, senders):
            return len(message.message)

        return self.dataCount(cc, senders, showMatched)


    def search(self, s, senders=[], ignoreCase=False, showMatched=False):
        def imc(message, senders):
            if ignoreCase:
                return int(s.lower() in message.message.lower())
                
            return int(s in message.message)
        
        return self.dataCount(imc, senders, showMatched)

    def searchRegex(self, regex, senders=[], ignoreCase=False, showMatched=False):
        if ignoreCase:
            regex = re.compile(regex, flags=re.IGNORECASE)
        else:
            regex = re.compile(regex)
            
        def imcr(message, senders):
            return int(regex.search(message.message) !=None)
        
        return self.dataCount(imcr, senders, showMatched)

    def messagescount(self, senders=[], showMatched=False):
        def mc(message, senders):
            return 1
        return self.dataCount(mc, senders, showMatched)

    def getMessages(self, senders=[], session=False):
        senders = stringlistToLower(senders)
        messages = []
        if not session:
            sessions = self
        else:
            sessions = [session]
            
        for session in sessions:
            for message in session.messages:
                if self.checkSender(message, senders):
                    messages.append(message)
        return messages

    def vocabcount(self, senders=[], coolreturn=False):
        f = open("words.txt")
        words = f.read().split()
        f.close()
        
        vocab = {}
        def vc(message, senders):
            ws = message.message.split()
            count = 0
            for word in ws:
                if inList(words, word.strip()):
                    if word in vocab:
                        vocab[word] += 1
                    else:
                        vocab[word] = 1
                        count += 1
            return count

        count = self.dataCount(vc, senders, False)
        if coolreturn:
            return vocab
        
        return count
