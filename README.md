# mycli with ssh proxy

Quick Start
-----------


```
$ git clone https://github.com/iubuntu/mycli.git
$ cd mycli
$ python setup.py build
$ python setup.py install
```


##  ssh forword

  When you use `ssh jump` the tool will connect a `tunnel` between `remote mysql server` and `local server` by `SSH` dynamic port forward in order to connect mysql that rejected remote connections , which means that it is super easy to connect cloud mysql by user named `'root'@'127.0.0.1'`


```

      Examples:
        - mycli -h my_host.com -P 5713 -u root  -j --sshport 40202 --sshusername "root" --sshkey "/home/mysql/.ssh/devops.pem"

```
## changing
- I have added four options to use ssh proxy, after I forked from https://github.com/dbcli/mycli.git
 
```
  -j, --jump TEXT               jump : using ssh connect remote mysql
  --sshport INTEGER             SSH Port number to use for connection. Honors
  --sshusername TEXT            User name to connect to the linux .
  --sshkey TEXT                 Privite ssh key when you use jumping .
  
```

## Important
- It is important to refer original documents  ` https://github.com/dbcli/mycli.git`