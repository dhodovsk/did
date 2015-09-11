# coding: utf-8

"""
Command line interface for did

This module takes care of processing command line options and
running the main loop which gathers all individual stats.
"""

from __future__ import unicode_literals, absolute_import

import re
import sys
import kerberos
import optparse
import ConfigParser
from dateutil.relativedelta import relativedelta as delta

import did.base
import did.utils as utils
from did.utils import log
from did.stats import UserStats
from did.base import ConfigError, ReportError


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Options
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class Options(object):
    """ Command line options parser """

    def __init__(self, arguments=None):
        """ Prepare the parser. """
        self.parser = optparse.OptionParser(
            usage="did [last] [week|month|quarter|year] [opts]",
            description=__doc__.strip())
        self.arguments = arguments

        # Time & user selection
        group = optparse.OptionGroup(self.parser, "Selection")
        group.add_option(
            "--email", dest="emails", default=[], action="append",
            help="User email address(es)")
        group.add_option(
            "--since",
            help="Start date in the YYYY-MM-DD format")
        group.add_option(
            "--until",
            help="End date in the YYYY-MM-DD format")
        self.parser.add_option_group(group)

        # Create sample stats and include all stats objects options
        log.debug("Loading Sample Stats group to build Options")
        self.sample_stats = UserStats()
        self.sample_stats.add_option(self.parser)

        # Display mode
        group = optparse.OptionGroup(self.parser, "Display mode")
        group.add_option(
            "--format", default="text",
            help="Output style, possible values: text (default) or wiki")
        group.add_option(
            "--width", default=did.base.Config().width, type="int",
            help="Maximum width of the report output (default: %default)")
        group.add_option(
            "--brief", action="store_true",
            help="Show brief summary only, do not list individual items")
        group.add_option(
            "--verbose", action="store_true",
            help="Include more details (like modified git directories)")
        group.add_option(
            "--total", action="store_true",
            help="Append total stats after listing individual users")
        group.add_option(
            "--merge", action="store_true",
            help="Merge stats of all users into a single report")
        group.add_option(
            "--debug", action="store_true",
            help="Turn on debugging output, do not catch exceptions")
        self.parser.add_option_group(group)

    def parse(self, arguments=None):
        """ Parse the options. """
        # Split arguments if given as string and run the parser
        if arguments is not None:
            self.arguments = arguments
        if (self.arguments is not None
                and isinstance(self.arguments, basestring)):
            self.arguments = self.arguments.split()
        (opt, arg) = self.parser.parse_args(self.arguments)

        # Enable debugging output
        if opt.debug:
            utils.Logging.set(utils.LOG_DEBUG)

        # Enable --all if no particular stat or group selected
        opt.all = not any([
            getattr(opt, stat.dest) or getattr(opt, group.dest)
            for group in self.sample_stats.stats
            for stat in group.stats])

        # Detect email addresses and split them on comma
        if not opt.emails:
            opt.emails = did.base.Config().email
        opt.emails = utils.split(opt.emails, separator=re.compile(r"\s*,\s*"))
        if not opt.emails:
            raise ConfigError("No email given. Use --email or create config.")

        # Time period handling
        if opt.since is None and opt.until is None:
            opt.since, opt.until, period = did.base.Date.period(arg)
        else:
            opt.since = did.base.Date(opt.since or "1993-01-01")
            opt.until = did.base.Date(opt.until or "today")
            # Make the 'until' limit inclusive
            opt.until.date += delta(days=1)
            period = "given date range"

        # Validate the date range
        if not opt.since.date < opt.until.date:
            raise RuntimeError(
                "Invalid date range ({0} to {1})".format(
                    opt.since, opt.until.date - delta(days=1)))
        print(u"Status report for {0} ({1} to {2}).".format(
            period, opt.since, opt.until.date - delta(days=1)))

        # Finito
        log.debug("Gathered options:")
        log.debug('options = {0}'.format(opt))
        return opt


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Main
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def main(arguments=None):
    """
    Parse options, gather stats and show the results

    Takes optional parameter ``arguments`` which can be useful for
    testing purposes. Function returns tuple of the form::

        ([user_stats], team_stats)

    with the list of all gathered stats objects.
    """
    try:
        # Parse options, initialize gathered stats
        options = Options().parse(arguments)
        gathered_stats = []

        # Check for user email addresses (command line or config)
        users = [did.base.User(email=email) for email in options.emails]

        # Prepare team stats object for data merging
        team_stats = UserStats(options=options)
        if options.merge:
            utils.header("Total Report")
            utils.item("Users: {0}".format(len(users)), options=options)

        # Check individual user stats
        for user in users:
            if options.merge:
                utils.item(user, 1, options=options)
            else:
                utils.header(user)
            user_stats = UserStats(user=user, options=options)
            user_stats.check()
            team_stats.merge(user_stats)
            gathered_stats.append(user_stats)

        # Display merged team report
        if options.merge or options.total:
            if options.total:
                utils.header("Total Report")
            team_stats.show()

        # Return all gathered stats objects
        return gathered_stats, team_stats

    except ConfigError as error:
        utils.info("Create at least a minimum config file {0}:\n{1}".format(
            did.base.Config.path(), did.base.Config().example().strip()))
        log.error(error)
        sys.exit(1)

    except ReportError as error:
        log.error(error)
        sys.exit(1)

    except kerberos.GSSError as error:
        log(error)
        log.error("Kerberos authentication failed. Try kinit.")
        sys.exit(2)
