from __future__ import with_statement

import os
import sys
import threading
import logging
import core

# number of log files to keep
NUM_LOGS = 3

# log size in bytes
LOG_SIZE = 10000000  # 10 megs

ERROR = logging.ERROR
WARNING = logging.WARNING
MESSAGE = logging.INFO
DEBUG = logging.DEBUG
POSTPROCESS = 21
DB = 5

reverseNames = {u'ERROR': ERROR,
                u'WARNING': WARNING,
                u'INFO': MESSAGE,
                u'DEBUG': DEBUG,
                u'POSTPROCESS': POSTPROCESS,
                u'DB': DB}

class NTMRotatingLogHandler(object):
    def __init__(self, log_file, num_files, num_bytes):
        self.num_files = num_files
        self.num_bytes = num_bytes

        self.log_file = log_file
        self.log_file_path = log_file
        self.cur_handler = None

        self.writes_since_check = 0

        self.console_logging = True
        self.log_lock = threading.Lock()

    def close_log(self, handler=None):
        if not handler:
            handler = self.cur_handler

        if handler:
            ntm_logger = logging.getLogger('nzbtomedia')
            pp_logger = logging.getLogger('postprocess')
            db_logger = logging.getLogger('db')

            ntm_logger.removeHandler(handler)
            pp_logger.removeHandler(handler)
            db_logger.removeHandler(handler)

            handler.flush()
            handler.close()

    def initLogging(self, consoleLogging=True):

        if consoleLogging:
            self.console_logging = consoleLogging

        old_handler = None

        # get old handler in case we want to close it
        if self.cur_handler:
            old_handler = self.cur_handler
        else:
            #Add a new logging levels
            logging.addLevelName(21, 'POSTPROCESS')
            logging.addLevelName(5, 'DB')

            # only start consoleLogging on first initialize
            if self.console_logging:
                # define a Handler which writes INFO messages or higher to the sys.stderr
                console = logging.StreamHandler()

                # log-level
                console.setLevel(DB)

                # set a format which is simpler for console use
                console.setFormatter(DispatchingFormatter(
                    {'nzbtomedia': logging.Formatter('[%(asctime)s] [%(levelname)s]::%(message)s', '%H:%M:%S'),
                     'postprocess': logging.Formatter('[%(asctime)s] [%(levelname)s]::%(message)s', '%H:%M:%S'),
                     'db': logging.Formatter('[%(asctime)s] [%(levelname)s]::%(message)s', '%H:%M:%S')
                    },
                    logging.Formatter('%(message)s'), ))

                # add the handler to the root logger
                logging.getLogger('nzbtomedia').addHandler(console)
                logging.getLogger('postprocess').addHandler(console)
                logging.getLogger('db').addHandler(console)

        self.log_file_path = os.path.join(core.LOG_DIR, self.log_file)

        self.cur_handler = self._config_handler()

        logging.getLogger('nzbtomedia').addHandler(self.cur_handler)
        logging.getLogger('postprocess').addHandler(self.cur_handler)
        logging.getLogger('db').addHandler(self.cur_handler)

        logging.getLogger('nzbtomedia').setLevel(logging.DEBUG)
        logging.getLogger('postprocess').setLevel(POSTPROCESS)
        logging.getLogger('db').setLevel(DB)

        # already logging in new log folder, close the old handler
        if old_handler:
            self.close_log(old_handler)

    def _config_handler(self):
        """
        Configure a file handler to log at file_name and return it.
        """

        file_handler = logging.FileHandler(self.log_file_path, encoding='utf-8')

        file_handler.setLevel(DB)

        file_handler.setFormatter(DispatchingFormatter(
            {'nzbtomedia': logging.Formatter('%(asctime)s %(levelname)-8s::%(message)s', '%Y-%m-%d %H:%M:%S'),
             'postprocess': logging.Formatter('%(asctime)s %(levelname)-8s::%(message)s', '%Y-%m-%d %H:%M:%S'),
             'db': logging.Formatter('%(asctime)s %(levelname)-8s::%(message)s', '%Y-%m-%d %H:%M:%S')
            },
            logging.Formatter('%(message)s'), ))

        return file_handler

    def _log_file_name(self, i):
        """
        Returns a numbered log file name depending on i. If i==0 it just uses logName, if not it appends
        it to the extension (blah.log.3 for i == 3)
        
        i: Log number to ues
        """

        return self.log_file_path + ('.' + str(i) if i else '')

    def _num_logs(self):
        """
        Scans the log folder and figures out how many log files there are already on disk

        Returns: The number of the last used file (eg. mylog.log.3 would return 3). If there are no logs it returns -1
        """

        cur_log = 0
        while os.path.isfile(self._log_file_name(cur_log)):
            cur_log += 1
        return cur_log - 1

    def _rotate_logs(self):

        ntm_logger = logging.getLogger('nzbtomedia')
        pp_logger = logging.getLogger('postprocess')
        db_logger = logging.getLogger('db')

        # delete the old handler
        if self.cur_handler:
            self.close_log()

        # rename or delete all the old log files
        for i in range(self._num_logs(), -1, -1):
            cur_file_name = self._log_file_name(i)
            try:
                if i >= NUM_LOGS:
                    os.remove(cur_file_name)
                else:
                    os.rename(cur_file_name, self._log_file_name(i + 1))
            except OSError:
                pass

        # the new log handler will always be on the un-numbered .log file
        new_file_handler = self._config_handler()

        self.cur_handler = new_file_handler

        ntm_logger.addHandler(new_file_handler)
        pp_logger.addHandler(new_file_handler)
        db_logger.addHandler(new_file_handler)

    def log(self, toLog, logLevel=MESSAGE, section='MAIN'):

        with self.log_lock:

            # check the size and see if we need to rotate
            if self.writes_since_check >= 10:
                if os.path.isfile(self.log_file_path) and os.path.getsize(self.log_file_path) >= LOG_SIZE:
                    self._rotate_logs()
                self.writes_since_check = 0
            else:
                self.writes_since_check += 1

            try:
                message = u"%s: %s" % (str(section).upper(), toLog)
            except:
                message = u"%s: Message contains non-utf-8 string" % (str(section).upper())

            out_line = message

            ntm_logger = logging.getLogger('nzbtomedia')
            pp_logger = logging.getLogger('postprocess')
            db_logger = logging.getLogger('db')
            setattr(pp_logger, 'postprocess', lambda *args: pp_logger.log(POSTPROCESS, *args))
            setattr(db_logger, 'db', lambda *args: db_logger.log(DB, *args))

            try:
                if logLevel == DEBUG:
                    if core.LOG_DEBUG == 1:
                        ntm_logger.debug(out_line)
                elif logLevel == MESSAGE:
                    ntm_logger.info(out_line)
                elif logLevel == WARNING:
                    ntm_logger.warning(out_line)
                elif logLevel == ERROR:
                    ntm_logger.error(out_line)
                elif logLevel == POSTPROCESS:
                    pp_logger.postprocess(out_line)
                elif logLevel == DB:
                    if core.LOG_DB == 1:
                        db_logger.db(out_line)
                else:
                    ntm_logger.info(logLevel, out_line)
            except ValueError:
                pass

    def log_error_and_exit(self, error_msg):
        log(error_msg, ERROR)

        if os.environ.has_key('NZBOP_SCRIPTDIR'):
            sys.exit(core.NZBGET_POSTPROCESS_ERROR)
        elif not self.console_logging:
            sys.exit(error_msg.encode(core.SYS_ENCODING, 'xmlcharrefreplace'))
        else:
            sys.exit(1)

class DispatchingFormatter:
    def __init__(self, formatters, default_formatter):
        self._formatters = formatters
        self._default_formatter = default_formatter

    def format(self, record):
        formatter = self._formatters.get(record.name, self._default_formatter)
        return formatter.format(record)

ntm_log_instance = NTMRotatingLogHandler(core.LOG_FILE, NUM_LOGS, LOG_SIZE)

def log(toLog, logLevel=MESSAGE, section='MAIN'):
    ntm_log_instance.log(toLog, logLevel, section)

def info(toLog, section='MAIN'):
    log(toLog, MESSAGE, section)

def error(toLog, section='MAIN'):
    log(toLog, ERROR, section)

def warning(toLog, section='MAIN'):
    log(toLog, WARNING, section)

def debug(toLog, section='MAIN'):
    log(toLog, DEBUG, section)

def postprocess(toLog, section='POSTPROCESS'):
    log(toLog, POSTPROCESS, section)

def db(toLog, section='DB'):
    log(toLog, DB, section)

def log_error_and_exit(error_msg):
    ntm_log_instance.log_error_and_exit(error_msg)

def close():
    ntm_log_instance.close_log()
