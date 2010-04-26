#!/bin/bash

#Use this file to set variables in config files rather than editing the config file directly.  
#This allows BCFG2 to use your values rather than replacing the file with our defaults.
#Any variable not set in this file (ie, left empty) receives the default value (often based on system memory size)

#/etc/apache2/apache2.conf
export APACHE_MAXCLIENTS=""

#/etc/apparmor.d/usr.sbin.mysqld
export APPARMOR_MYSQLD=""

#/etc/default/tomcat6
export TOMCAT_MEMORY=""

#/etc/default/varnish
export VARNISH_MEMORY=""

#/etc/memcached.conf
export MEMCACHED_MEMORY=""

#/etc/mysql/my.cnf
export INNODB_BUFFER_POOL_SIZE=""
export KEY_BUFFER_SIZE=""
export MYSQL_MAX_CONNECTIONS=""

#/etc/php5/apache2/php.conf
export PHP_MEMORY=""

#/etc/php5/conf.d/apc.ini
export APC_MEMORY=""

#/etc/tomcat6/server.xml
export TOMCAT_MAX_THREADS=""

#/etc/varnish/default.vcl
export VARNISH_VCL_ERROR=""
export VARNISH_VCL_FETCH=""
export VARNISH_VCL_HASH=""
export VARNISH_VCL_RECV=""

