#!/bin/sh

set -e

make-deb
cd debian

cat > postinst <<- EOM
#!/bin/bash

echo "Setting up symlink to mycli"
ln -sf /usr/share/python/mycli/bin/mycli /usr/local/bin/mycli
EOM
echo "Created postinst file."

cat > postrm <<- EOM
#!/bin/bash

echo "Removing symlink to mycli"
rm /usr/local/bin/mycli
EOM
echo "Created postrm file."

for f in *
do
    echo "" >> $f;
done

echo "INFO: debian folder is setup and ready."
echo "INFO: 1. Update the changelog with real changes."
echo "INFO: 2. Run:\n\tvagrant provision || vagrant up"
