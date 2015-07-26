#!/bin/sh
make-deb
cd debian

cat > postinst <<- EOM
#!/bin/bash

echo "Setting up symlink to mycli"
ln -sf /usr/share/python/mycli/bin/mycli /usr/local/bin/mycli
EOM

cat > postrm <<- EOM
#!/bin/bash

echo "Removing symlink to mycli"
rm /usr/local/bin/mycli
EOM

for f in *
do
    echo "" >> $f;
done

vagrant up
