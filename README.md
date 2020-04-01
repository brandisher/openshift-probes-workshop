# openshift-probes-sandbox
A sandbox for OpenShift users to test out different liveness/readiness probe failure conditions.

# Creating the Sandbox
While logged into an OpenShift cluster, run `oc new-app python~https://github.com/brandisher/openshift-probes-sandbox.git`.  If the python image stream is not available, you can use any image with Python 3.6 or better.

# Deleting the Sandbox
`oc delete all -l app=openshift-probes-sandbox`
