from __future__ import with_statement
from fabric.api import *
from urlparse import urlparse
from os.path import exists
from string import Template

def unarchive(archive, destination):

    if exists(destination):
        local("rm -rf " + destination)

    local("bzr init " + destination)

    with cd(destination):
        local("bzr import " + archive)
        local("rm -r ./.bzr")
        local("find . -depth -name .svn -exec rm -fr {} \;")
        local("find . -depth -name CVS -exec rm -fr {} \;")

def is_valid_db(db_info):

    # Check for problems
    if db_info['username'] == None or db_info['password'] == None or db_info['database'] == None:
        # Invalid db connection string (missing information)
        return False
    elif db_info['username'] == "username" and db_info['password'] == "password" and db_info['database'] == "databasename":
        # Connection string is still set to default values
        return False
    elif  ['/','\\','.'] in db_info['database']:
        # Invalid characters in database name
        return False
    else:
        return True

def get_db(settings_path):

    url = local("awk '/^\$db_url = /' " + settings_path + " | sed 's/^.*'\\''\([a-z]*\):\(.*\)'\\''.*$/\\2/'")
    if url.endswith('\n'):
        url = url[:-1]

    # Check for multiple connection strings. If more than one, use the last.
    if '\n' in url:
        url = url.split('\n')
        url = urlparse(url[len(url)-1])
    else:
        url = urlparse(url)

    db_info = {}
    db_info['username'] = url.username
    db_info['password'] = url.password
    db_info['database'] = url.path[1:].replace('\n','')

    return db_info

def get_settings(working_dir):

    db_info = {}
    # Get all settings.php files and put into list
    with cd(working_dir):
        settings_files = local('find sites/ -name settings.php -type f')
    if settings_files.endswith('\n'):
        settings_files = settings_files[:-1]

    # Check if any settings.php files were found
    if not settings_files:
        return False

    # multiple settings.php files
    if '\n' in settings_files:
        match = None
        settings_files = settings_files.split('\n')
        # Step through each settings.php file and select a valid settings.php (with preference for sites/default/)
        for sfile in settings_files:
            db_info = get_db(working_dir + sfile)
            if is_valid_db(db_info):
                if sfile.find('/default/') != -1:
                    return db_info
                match = db_info
        if match:
            return match
        else:
            # No valid settings.php found
            return False

    # Single settings.php
    else:
        db_info = get_db(working_dir + settings_files)
        if is_valid_db(db_info):
            return db_info
        else:
            # No valid settings.php found
            return False



def get_env_vars():
    '''Get distribution name and return environmental variables based on distribution defaults.'''
    #TODO: Do we need more specific ubuntu versions (e.g. check for lucid for upstart services?)
    ret = {}
    # Default Ubuntu
    if exists('/etc/debian_version'):
        ret['webroot'] = '/var/www/'
        ret['owner'] = 'root'
        ret['group'] = 'www-data'
        ret['distro'] = 'ubuntu'
    # Default Centos
    elif exists('/etc/redhat-release'):
        ret['webroot'] = '/var/www/html/'
        ret['owner'] = 'root'
        ret['group'] = 'apache'
        ret['distro'] = 'centos'
    return ret

def get_branch_and_revision(working_dir):
    #TODO: pressflow.txt  doesn't exists if pulled from bzr
    #TODO: check that it is Drupal V6
    ret = {}
    if exists(working_dir + "PRESSFLOW.txt"):
        rev = local("cat " + working_dir + "PRESSFLOW.txt").split('.')[2]
        ret['branch'] = "lp:pressflow/6.x"
        ret['revision'] = rev.replace('\n','')
        ret['type'] = "PRESSFLOW"
    else:
        rev = local("cat " + working_dir  + "CHANGELOG.txt | grep --max-count=1 Drupal | sed 's/Drupal \([0-9]\)*\.\([0-9]*\).*/\\1-\\2/'")
        ret['branch'] = "lp:drupal/6.x-stable"
        ret['revision'] = "tag:DRUPAL-" + rev.replace('\n','')
        ret['type'] = "DRUPAL"
    return ret

def import_database(db_info, working_dir):
    #TODO: test for multiple .sql files
    #TODO: test for no .sql files
    db_dump_file = local("ls " + working_dir + "*.sql")
    local("mysql -u root -e 'CREATE DATABASE IF NOT EXISTS " + db_info['database'] + "'")
    local("mysql -u root -e \"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, LOCK TABLES, CREATE TEMPORARY TABLES ON " + db_info['database'] + ".* TO '" + db_info['username'] + "'@'localhost' IDENTIFIED BY '" + db_info['password'] + "';\"")
    local("mysql -u root -e 'FLUSH PRIVILEGES;'")
    local("mysql -u root " + db_info['database'] + " < " + db_dump_file)
    local("rm -f " + db_dump_file)

def setup_site_files(webroot, working_dir):
    #TODO: add large file size sanity check (no commits over 20mb)
    #TODO: sanity check for versions prior to 6.6 (no pressflow branch).
    #TODO: test wildcard in ignore
    #TODO: look into ignoreing files directory
    #TODO: sanity check for conflicts (hacked core)
    #TODO: check if updatedb needs to run. Fabric will return error if it doesn't need to run.

    if exists(webroot):
        local('rm -r ' + webroot)

    # Create vanilla drupal/pressflow branch of same version as import site
    version = get_branch_and_revision(working_dir)
    local("bzr branch -r " + version['revision'] + " " + version['branch'] + " " + webroot)

    # Bring import site up to current Pressflow version
    with cd(webroot):

        # Import site and revert any changes to core
        local("bzr import " + working_dir)
        reverted = local("bzr revert")

        # Cleanup potential issues
        local("rm -f PRESSFLOW.txt")
        #if exists(".bzrignore"):
        #    local('bzr revert .bzrignore')

        # Magic Happens
        #local("bzr add")
        local("bzr commit --unchanged -m 'Automated Commit'")
        local("bzr merge lp:pressflow/6.x")
        local("rm -r ./.bzr")
#local("bzr commit --unchanged -m 'Update to latest Pressflow core'")
        
        # Run update.php
        local("drush -y updatedb")

        # Save reverted files as hudson build artifacts
        with open('/var/lib/hudson/jobs/import_site/workspace/reverted.txt', 'w') as f:
            f.write(reverted)
        f.close

def update_settings(webroot, db_info):
    #TODO: remove any previously defined $db_url strings rather than relying on ours being last
    slug = Template(local("cat /etc/mercury/templates/mercury.settings.php"))
    slug = slug.safe_substitute(db_info)
    with open(webroot + "sites/default/settings.php", 'a') as f:
        f.write(slug)
    f.close

def setup_modules(webroot):

    required_modules = {'apachesolr':None, 'apachesolr_search':None, 'cookie_cache_bypass':None, 'locale':None, 'memcache_admin':None, 'syslog':None, 'varnish':None}

    with cd(webroot):
        #TODO: extend drush so that "drush pm-list" can have xml/json friendly output. Below is temporary stop-gap

        # Output module status in dictionary friendly format.
        site_modules = local("drush sql-query \"SELECT name, status FROM system WHERE type='module';\" | awk -v sq=\"'\" '{if ($1 != \"name\" && $2 == 1) print \"(\"sq$1sq\", \"sq\"Enabled\"sq\")\"; if ($1 != \"name\" && $2 == 0) print \"(\"sq$1sq\", \"sq\"Disabled\"sq\")\" }'").replace('\n',',')[:-1]
        # Create module dictionary. Key=Module name, Value=Enabled/Disabled/None
        site_modules = dict(eval(site_modules))

        # If a required module is found, the value is set to site_modules current status (Enabled/Disabled). If not found, value=None.
        for name in required_modules.keys():
            if site_modules.has_key(name):
                required_modules[name] = site_modules[name]

        # Special case: download memcache if memcache_admin doesn't exist, but don't enable memcache_admin.
        if required_modules['memcache_admin'] == None:
            local("drush -y dl memcache")
            del(required_modules['memcache_admin'])
    
        # Special Case: Make sure both apachesolr and apachesolr_search are installed and enabled.
        if required_modules['apachesolr'] == None:
            local("drush -y dl apachesolr")
            required_modules['apachesolr'] = 'Disabled'
            required_modules['apachesolr_search'] = 'Disabled'
        if required_modules['apachesolr'] == 'Disabled':
            local("wget http://solr-php-client.googlecode.com/files/SolrPhpClient.r22.2009-11-09.tgz")
            local("mkdir -p ./sites/all/modules/apachesolr/SolrPhpClient/")
            local("tar xzf SolrPhpClient.r22.2009-11-09.tgz -C ./sites/all/modules/apachesolr/")
            local("drush -y en apachesolr")
            del(required_modules['apachesolr'])
        if required_modules['apachesolr_search'] == 'Disabled':
            local("drush -y en apachesolr_search")
            del(required_modules['apachesolr_search'])

        # Normal Cases: Download if absent & enable if disabled.
        for module, status in required_modules.iteritems():
            if status == None:
                local("drush -y dl " + module)
                status = 'Disabled' 
            if status == 'Disabled':
                local("drush -y en " + module)

        # Set apachesolr variables
        local("drush php-eval \"variable_set('apachesolr_path', '/default');\"")
        local("drush php-eval \"variable_set('apachesolr_port', 8983);\"")
        local("drush php-eval \"variable_set('apachesolr_search_make_default', 1);\"")
        local("drush php-eval \"variable_set('apachesolr_search_spellcheck', TRUE);\"")

        # Set admin/settings/performance variables
        local("drush php-eval \"variable_set('cache', CACHE_EXTERNAL);\"")
        local("drush php-eval \"variable_set('page_cache_max_age', 900);\"")
        local("drush php-eval \"variable_set('block_cache', TRUE);\"")
        local("drush php-eval \"variable_set('page_compression', 0);\"")
        local("drush php-eval \"variable_set('preprocess_js', TRUE);\"")
        local("drush php-eval \"variable_set('preprocess_css', TRUE);\"")

def set_permissions(site_info):

    # setup ownership and permissions
    local('chown -R ' + site_info['owner'] + ':' + site_info['group'] + ' ' + site_info['webroot'])
    local('chmod 440 ' + site_info['webroot'] + 'sites/default/settings.php')

    #TODO: where do we want to set the start point for searching for 'files' directories (to change perms)?
    # make sure everything under the 'files' directory has proper perms (770 on dirs, 550 on files)
    with cd(site_info['webroot'] + '/sites/'):
        local("find . -type d -name files -exec chmod ug=rwx,o= '{}' \;")
        local("find . -name files -type d -exec find '{}' -type f \; | while read FILE; do chmod ug=rw,o= \"$FILE\"; done")
        local("find . -name files -type d -exec find '{}' -type d \; | while read DIR; do chmod ug=rwx,o= \"$DIR\"; done")

def restart_services(distro):
    if distro == 'ubuntu':
        local('/etc/init.d/apache2 restart')
        local('/etc/init.d/memcached restart')
        local('/etc/init.d/tomcat6 restart')
    elif distro == 'centos':
        local('/etc/init.d/httpd restart')
        local('/etc/init.d/memcached restart')
        local('/etc/init.d/tomcat5 restart')

def import_site(site_archive, working_dir='/tmp/import_site/'):
    
    unarchive(site_archive, working_dir)

    settings_info = get_settings(working_dir)
    site_info = get_env_vars()

    import_database(settings_info, working_dir)
    setup_site_files(site_info['webroot'], working_dir)
    setup_modules(site_info['webroot'])
    update_settings(site_info['webroot'], settings_info)
    set_permissions(site_info)
    restart_services(site_info['distro'])

    #TODO: Write cleanup function
    #TODO: clear solr index (if exists) before using new site

