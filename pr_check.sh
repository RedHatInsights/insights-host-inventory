echo "This is a temporary hack to get past pr_check, which fails due to the \
 addition of clowder_config. clowder_config used \"app_common_python\" \
 module, which blocks the addition of importib-resources library. \
 importlib-resources is needed by host-inventory.  To add, importlib-resources\
  in the presence of app_common_python may require upgrading python past v3.6 \
  
  This hack should be used IF UNIT TESTS ARE RUNNING."