# Summary of changes

## v1.0.0

This has breaking changes for this interface. All screen templates have been modified to a new structure (not the ideal)
with new layouts and data format. All those changes are based on Bootstrap 4 available components.

This is far from a ideal dashboard or something like that. This is just a base form of what Wharf can be delivering to new users without much effort.

The new template and static structure is not even the ideal for front end constructions or Django applications, but this release objective is to show and try to make changes to the Wharf base.

This new release brings this modifications:

1. **Login screen**:
  * There is a new login screen, with a new addition: there two new dismissible alerts for ADMIN_LOGIN and ADMIN_PASSWORD and user/password incorrect;
  
  * The screen was based on full center layout from Bootstrap examples;
  
2. **Server connection setup screen**:
  * There is a new SSH keys setup screen, base on full center layout from Bootstrap examples;
  
  * This new screen makes the SSH key more noticeable with few lines of instructions and a link to official documentation;
  
3. **App listing**:

  * There is a navbar that contains a link to the home page, and the button _Refresh Dokku information_ on the right side;
  
  * The new Applications section:
  
    * The tab _Apps list_ lists all the apps from Dokku;
    * The tab _Add new item_ allows the user to create a new Dokku app, using the same form from before;
  
  * The new Global configuration section:
    
    * The tab _Global configuration item list_ lists all the environment variables defined as global for Dokku;
    * The tab _Add new item_ allows the user to create a new environment variable for Dokku global configuration;
  
4. **The app information screen**:

  * Now _Actions_, _Task logs_, _Process Info_ and _Processes_ have their own sections to display information, always on top;
  
  * The _Log output_ section is with a new visual, to be more readable and noticeable when the user enters the screen;
  
  * The _App links_ section now shows the app links in tabs for links types:
  
    * Postgres;
    
    * Redis;
    
    * MariaDB (new);
    
  * The new _App links_ section now shows the links for each type in a table;
  
  * The new _App links_ section shows more information about the links this app have, and now allows the users to remove this links from the app;
  
  * The _Domains and SSL_ section shows all the information about the domains and Let's encrypt information/actions:
  
    * The tab _Domains for this app_ lists all linked domains for the app in a table, and allows the user to delete the respective domain in the row;
    
    * The tab _Add new domain_ allows the user to create a new domain to that app, with the same form from before;
    
    * The tab _Let's Encrypt_ status shows all the information about Let's Encrypt status, or displays the form to create a SSL certificate, with the same form from before;
    
  * The _App environment config_ section now shows all information about the environment variables from this app:
  
    * The tab _Configuration list for this app_ lists in a table all the environment variables already defined for this app;
    
    * The tab _Add new item_ allows the user to create a new item to environment variables configuration with the same form from before;
    
5. **The task log detail/wait command screen**:

    * The new screen now have two main sections: the top navbar with the information about the task and the Log output section;
    
6. **The notifications**

    * The notifications listing was disabled (too buggy to be implemented yet), but it is in progress to a new notification format;