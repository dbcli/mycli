from datetime import datetime
import re

class ColoredPrompt:

    # Almost useless
    colors = {
        "black": "k",
        "red": "r",
        "green": "g",
        "yellow": "y",
        "blue": "b",
        "magenta": "m",
        "cyan": "c",
        "white": "w"
    }

    standard = {
        'base': "#ffffff",
        'engine': "#ffffff",
		"user": "#ffffff",
		"host": "#ffffff",
		"database": "#ffffff",
        "date": "#ffffff",
        "dsn": "#ffffff",
        "port": "#ffffff",
        "separator.first": "#ffffff",
        "separator.second": "#ffffff",
        "separator.third": "#ffffff",
		"separator.forth": "#ffffff",
		"separator.fifth": "#ffffff"
    }

    def __init__(self, context):
        self.context = context

    def get_prompt(self, string, colored=False):
        sqlexecute = self.context.sqlexecute
        host = self.context.login_path if self.context.login_path and self.context.login_path_as_host else sqlexecute.host

        if colored:
            return self.get_color_prompt(string,
                                         user=sqlexecute.user,
                                         host=host,
                                         port=sqlexecute.port,
                                         engine=sqlexecute.server_type()[0],
                                         database=sqlexecute.dbname,
                                         dsn=self.context.dsn_alias)
        else:
            return self.get_simple_prompt(string,
                    user=sqlexecute.user,
                    host = host,
                    port = sqlexecute.port,
                    engine = sqlexecute.server_type()[0],
                    database = sqlexecute.dbname,
                    dsn = self.context.dsn_alias)

    def get_simple_prompt(self, string, user='(none)', host='(none)', engine='mycli', database='(none)', dsn='(none)', port=3306):
        now = datetime.now()

        string = string.replace('\\u', user or '(none)')
        string = string.replace('\\h', host or '(none)')
        string = string.replace('\\d', database or '(none)')
        string = string.replace('\\t', engine or 'mycli')
        string = string.replace('\\n', "\n")
        string = string.replace('\\D', now.strftime('%a %b %d %H:%M:%S %Y'))
        string = string.replace('\\m', now.strftime('%M'))
        string = string.replace('\\P', now.strftime('%p'))
        string = string.replace('\\R', now.strftime('%H'))
        string = string.replace('\\r', now.strftime('%I'))
        string = string.replace('\\s', now.strftime('%S'))
        string = string.replace('\\p', str(port))
        string = string.replace('\\A', dsn or '(none)')
        string = string.replace('\\_', ' ')

        # Separator are for colors only
        string = re.sub(r'\\[1-5]', '', string)
        return string

    def getStyled(self, style="base", content=''):
        return ("class:{}".format(style), content)

    def get_color_prompt(self, string, user='(none)', host='(none)', engine='mycli', database='(none)', dsn='(none)', port=3306):
        now = datetime.now()

        currentStyle = 'base'
        prompt = [self.getStyled()]
        for fragment in re.split(r'(\\[a-zA-Z1-5_\\])', string):
            if fragment.startswith('\\u'):
                currentStyle = 'user'
                prompt.append(self.getStyled(currentStyle, user or '(none)'))
            elif fragment.startswith('\\h'):
                currentStyle = 'host'
                prompt.append(self.getStyled(currentStyle, host or '(none)'))
            elif fragment.startswith('\\d'):
                currentStyle = 'database'
                prompt.append(self.getStyled(currentStyle, database or '(none)'))
            elif fragment.startswith('\\t'):
                currentStyle = 'engine'
                prompt.append(self.getStyled(currentStyle, engine or 'mycli'))
            elif fragment.startswith('\\p'):
                currentStyle = 'port'
                prompt.append(self.getStyled(currentStyle, str(port)))
            elif fragment.startswith('\\A'):
                currentStyle = 'dsn'
                prompt.append(self.getStyled(currentStyle, dsn or '(none)'))

            elif fragment.startswith('\\D'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%a %b %d %H:%M:%S %Y')))
            elif fragment.startswith('\\m'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%M')))
            elif fragment.startswith('\\P'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%p')))
            elif fragment.startswith('\\R'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%H')))
            elif fragment.startswith('\\r'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%I')))
            elif fragment.startswith('\\s'):
                currentStyle = 'date'
                prompt.append(self.getStyled(currentStyle, now.strftime('%S')))

            elif fragment.startswith('\\_'):
                prompt[-1] = self.getStyled(currentStyle, prompt[-1][1] + ' ')
            elif fragment.startswith('\\n'):
                prompt[-1] = self.getStyled(currentStyle, prompt[-1][1] + "\n")

            elif fragment.startswith('\\1'):
                currentStyle = 'separator.first'
                prompt.append(self.getStyled(currentStyle))
            elif fragment.startswith('\\2'):
                currentStyle = 'separator.second'
                prompt.append(self.getStyled(currentStyle))
            elif fragment.startswith('\\3'):
                currentStyle = 'separator.third'
                prompt.append(self.getStyled(currentStyle))
            elif fragment.startswith('\\4'):
                currentStyle = 'separator.forth'
                prompt.append(self.getStyled(currentStyle))
            elif fragment.startswith('\\5'):
                currentStyle = 'separator.fifth'
                prompt.append(self.getStyled(currentStyle))

            else:
                prompt[-1] = self.getStyled(currentStyle, prompt[-1][1] + fragment)
        return prompt