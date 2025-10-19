# meshtastic-commander

simple command runner on keyword, edit the config file enter the IP of your meshtastic wifi/network connected node. the channel ID you want it to listen to and the keywords/scripts you want it to run on. fully open source.
REQUIRES meshtastic-python 2.6.4-1+

you can pass variables to your scripts by adding them after the keyword and using "var:" to prepend them
for example

meshtastic keyword in this case is "test"

>test var:hello

with a shell script of
>#!/bin/bash
>echo $1

will simply give an output of "hello"

