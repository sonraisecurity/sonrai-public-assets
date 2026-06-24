Some of our users have run into conflicts between Sonrai CPF & AWS ControlTower/LandingZone.  

This "conflict" is due to how ControlTower deploys it's own managed permission sets. In some cases, when
CT is creating it's 6 default permission sets, it attempts to attach them to the Sonrai CMPs before they 
exist, because CT is running and creating permission sets, before CloudFormation can deploy the CPF
stackset & CMPs, before they are referenced. 

This script can be used to -detach- the CMPs from the permission sets prior to creating the account, and 
then putting the CMPs back in place after the account has been created. 


```
bash-5.2$ python ControlSonraiCMPs.py
usage: ControlSonraiCMPs.py [-h] [--detach | --attach]

Detach or attach Sonrai customer-managed policies on AWS Control Tower permission sets across all Identity Center instances/regions.

options:
  -h, --help  show this help message and exit
  --detach    Detach SonraiCMPs from AWS Control Tower permission sets
  --attach    Re-attach SonraiCMPs to AWS Control Tower permission sets (undo)
```
