# Openshift Probes Self-Led Workshop
The intent of this workshop is to provide a hands-on look into OpenShift/Kubernetes probes.

## Prerequisites
* You have an OpenShift cluster with access to Github.
* You have a namespace to create the workshop in.
* You have the OpenShift Client (`oc`) and `jq` installed.
  * [Install oc](https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html#installing-the-cli)
  * [Install jq](https://stedolan.github.io/jq/download/)

### Workarounds
* If you do not have access to Github from your OpenShift cluster, then clone the repository locally and push it to your own registry.  You'll need to adjust the workshop creation command to point to your mirrored repository.
* If you do not have access to the python image stream on OpenShift, you'll need to create your own image or use a python image that has python 3.6+ available.  Your image will need to run `pip install -r requirements.txt` and the command will be `python app.py`.

### Create the workshop
While logged into an OpenShift cluster, run `oc new-app python~https://github.com/brandisher/openshift-probes-workshop.git --name=workshop`.

### Delete the workshop
Run `oc delete all -l app=workshop` to delete all of the resources created for this specific app.  This can be done as a reset between testing each scenario or at the end of testing all of the scenarios as a clean up step.

# Start

## What does a successful readiness probe look like?
First, let's start by creating a successful readiness probe.

```
$ oc set probe dc/workshop --readiness --get-url=http://:8080
```

This will set the readiness probe to check `http://[pod IP]:8080` in the container defined in the deployment configuration.  The next step is to check the deploymentconfig to see what was actually created.

```
$ oc get dc -o yaml | grep readiness -A 8
          readinessProbe:
            failureThreshold: 3
            httpGet:
              path: /
              port: 8080
              scheme: HTTP
            periodSeconds: 10
            successThreshold: 1
            timeoutSeconds: 1
```
Openshift has some helpful defaults that may vary a bit depending on what version you're running, but generally it should look like the above example.  Next, we'll break down what we're seeing in this YAML.

`readinessProbe:` - This is the probe type and is the start of the YAML stanza that defines its configuration.  If you set a liveness probe, you'll see `livenessProbe:`.

`failureThreshold: 3` - This is the number of times the probe can fail before being considered a confirmed failure which generates an event.  "3" is the default.

`httpGet:` - This is the method used to check the application.  In addition to http, there are also container execution checks and tcp socket checks.

`path: /` - This is the application path that will be probed.

`port: 8080` - This is the port that will be probed.  Its important to note that this is the internal port for the container and not the port used for the route.

`scheme: HTTP` - This is the scheme that will be used for the request and is generally HTTP for healthchecks but it can also be https.

`periodSeconds: 10` - This is the interval at which the kubelet should execute the probe; every 10 seconds in this case.  "10" is the default.

`successThreshold: 1` - This is the number of times the probe needs to succeed in order to be considered a confirmed success.  "1" is the default.

`timeoutSeconds: 1` - This is the number of seconds the kubelet will wait for the probe to succeed.  "1" is the default.

Now that our readiness probe is configured and presumably successful, we need a way to confirm that its successful.  A succesful readiness probes won't generate events so `oc get events` won't help us here.  The easiest way to check is to grab the pod logs to see the HTTP requests being made and coming back with an HTTP 200 code.

```
$ oc logs dc/workshop
---> Running application from Python script (app.py) ...
 * Serving Flask app "app" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:8080/ (Press CTRL+C to quit)
10.129.0.1 - - [02/Apr/2020 18:15:07] "GET / HTTP/1.1" 200 -
10.129.0.1 - - [02/Apr/2020 18:15:17] "GET / HTTP/1.1" 200 -
10.129.0.1 - - [02/Apr/2020 18:15:27] "GET / HTTP/1.1" 200 -
...
```

### Warning due to a redirect
Technically, a probe will be considered a success of the HTTP response code is between 200 and 399 but a redirect will generate a probe warning event.

```
$ oc set probe dc/workshop --readiness --get-url=http://:8080/redirect
deploymentconfig.apps.openshift.io/workshop probes updated
```
Now check the events.
```
$ oc get events -o json --sort-by='{.metadata.creationTimestamp}' | jq '.items[] | select(.message | contains("probe warning")).message' | tail -n 1
"Readiness probe warning: <!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 3.2 Final//EN\">\n<title>Redirecting...</title>\n<h1>Redirecting...</h1>\n<p>You should be redirected automatically to target URL: <a href=\"https://www.example.com\">https://www.example.com</a>.  If not click the link."
```

## What does a failing readiness probe look like?
There are several conditions that can cause a readiness probe to fail, so we'll try to cover the most common failures in this section.

### Failure due to incorrect port
To test this, we'll need to break our probe and wait for the pod to restart.  For this test, we'll just change `:8080` to `:8081`.

```
$ oc set probe dc/workshop --readiness --get-url=http://:8081
deploymentconfig.apps.openshift.io/workshop probes updated
```

The simplest way to check for the failure is to do `oc get events -w` and watch for the probe failures.  Depending on the number of cluster workloads you could have a lot of events to sift through so let's filter through the events based on their message.

```
$ oc get events -o json --sort-by='{.metadata.creationTimestamp}' | jq '.items[] | select(.message | contains("probe failed")).message' | tail -n 1
"Readiness probe failed: Get http://10.129.0.56:8081/: dial tcp 10.129.0.56:8081: connect: connection refused"
```

Now we can see that the connection is being refused and generating an event. Since the connection is failing to establish, we don't see any logs in the pod.

```
$ oc logs dc/workshop
---> Running application from Python script (app.py) ...
 * Serving Flask app "app" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:8080/ (Press CTRL+C to quit)
 ```

 A side effect of the readiness probe not succeeding is that while the new pod will spin up and be working, it won't be marked as Ready and will stop the deploy pod from finishing the scale down of the old pod and the scale up of the new pod.  Eventually the deployment of the new pod will timeout/fail and you'll see a message like this in the deploy pod logs: `error: timed out waiting for any update progress to be made`.

### Failure due to incorrect HTTP scheme or certificate issues
To test this, we'll change our `--get-url` parameter from `http:` to `https:`

```
$ oc set probe dc/workshop --readiness --get-url=https://:8080
deploymentconfig.apps.openshift.io/workshop probes updated
```

An event should be recorded for this failure, so let's check the most recent event.

```
$ oc get events -o json --sort-by='{.metadata.creationTimestamp}' | jq '.items[] | select(.message | contains("probe failed")).message' | tail -n 1

"Readiness probe failed: Get https://10.129.0.76:8080/: tls: first record does not look like a TLS handshake"
```

We see a TLS handshake error because this endpoint that we're checking doesn't have a certificate.  If we check the logs of the pod that's marked as Running but not ready yet, we'll see failure indications in the logs as well.

```
$ oc logs dc/workshop
---> Running application from Python script (app.py) ...
 * Serving Flask app "app" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:8080/ (Press CTRL+C to quit)
10.129.0.1 - - [02/Apr/2020 20:17:01] code 400, message Bad request syntax ('\x16\x03\x01\x00Ð\x01\x00\x00Ì\x03\x03´\x91®Û\x16\x88\x86\xad\x9a!\tgÛ\x92\x14ÿ\x80!Ñ¸Þ\x17£õ\x91wH8[ÚR\x1c àTG\x1aÓ\x8c\x1dË\x04\x04\x9eô9\x99©\x955î½\x01KT(\x84æ\xa0\x97\x96Ît+\x14\x00 À/À0À+À,Ì¨Ì©À\x13À\tÀ\x14À')
10.129.0.1 - - [02/Apr/2020 20:17:01] "ÐÌ´®Û­!  gÛÿ!Ñ¸Þ£õwH8[ÚR àTGÓË9©5î½KT(
                                                                             æ Ît+ À/À0À+À,Ì¨Ì©ÀÀ       ÀÀ" HTTPStatus.BAD_REQUEST -
10.129.0.1 - - [02/Apr/2020 20:17:11] code 400, message Bad request syntax ('\x16\x03\x01\x00Ð\x01\x00\x00Ì\x03\x03úì,âWÐ\x11W©£\x0bP\x9d·¼i\x93Z7ý\x02\x03\x95\x92²%\x83ç¥üãÕ §Ðµ\x90\x07\x19N+\\ª¡0GçNXq\t\x8cF®\x1dæ¾\x1anÍäÖ-ýñ\x00 À/À0À+À,Ì¨Ì©À\x13À\tÀ\x14À')
10.129.0.1 - - [02/Apr/2020 20:17:11] "ÐÌúì,âWÐW©£
                                                  PZ7ý²%ç¥üãÕ §ÐµF®æ¾nÍäÖ-ýñ À/À0À+À,Ì¨Ì©ÀÀ     ÀÀ" HTTPStatus.BAD_REQUEST -
10.129.0.1 - - [02/Apr/2020 20:17:21] code 400, message Bad request syntax ('\x16\x03\x01\x00Ð\x01\x00\x00Ì\x03\x03×:³0]\x86>) }\x7fwlQÍ\x04¥bøõ¹Ì#Âü¤\x83!\x99\x1dØ® Íw`¬Ôø\x0c¨\x1db\x13"²\x0b^°ÅÁo³:HÐ®Ë\x13[W\x17\x92QT\x00 À/À0À+À,Ì¨Ì©À\x13À\tÀ\x14À')
10.129.0.1 - - [02/Apr/2020 20:17:21] "ÐÌ×:³0]>) }wlQÍ¥bøõ¹Ì#Âü¤!Ø® Íw`¬Ôø
                                                                          ¨b"²
                                                                              ^°ÅÁo³:HÐ®Ë[WQT À/À0À+À,Ì¨Ì©ÀÀ    ÀÀ" HTTPStatus.BAD_REQUEST -
10.129.0.1 - - [02/Apr/2020 20:17:31] code 400, message Bad request syntax ('\x16\x03\x01\x00Ð\x01\x00\x00Ì\x03\x03$\x15°\x99d¹\x82máÀï\x92[\x9f62\t\'\x8au\'AÁþK|\x9bÙ~"T\x86 éB\x18\x911\x8e«X\x84ç©1§\x134¥\x87\x9dY\x07ëÞs\x05_8hk\x11v¼¾\x00 À/À0À+À,Ì¨Ì©À\x13À\tÀ\x14À')
10.129.0.1 - - [02/Apr/2020 20:17:31] "ÐÌ$°d¹máÀï[u'AÁþK|~"T éB1«X
                                                                  ç©1§4¥ëÞs_8hkv¼¾ À/À0À+À,Ì¨Ì©ÀÀ       ÀÀ" HTTPStatus.BAD_REQUEST -
```

### Failure due to slow application startup time

Let's see what happens when we point the readiness probe at an endpoint with a 5 second startup delay.

```
$ oc set probe dc/workshop --readiness --get-url=http://:8080/5s_delay
deploymentconfig.apps.openshift.io/workshop probes updated
```

Now we check the events to see what the probe failure is:
```
$ oc get events -o json --sort-by='{.metadata.creationTimestamp}' | jq '.items[] | select(.message | contains("probe failed")).message' | tail -n 1
"Readiness probe failed: Get http://10.129.0.88:8080/5s_delay: net/http: request canceled (Client.Timeout exceeded while awaiting headers)"
```

To fix this slow startup time, we need to tell the kubelet to wait before attempting the initial probe by adding `--initial-delay-seconds=` to our probe definition.  We have to also add `--timeout-seconds=15` to ensure that the probe won't timeout before its first run.
```
oc set probe dc/workshop --readiness --get-url=http://:8080/5s_delay --initial-delay-seconds=10 --timeout-seconds=15
```

After the pod is redeployed, you'll notice that no intial probe error occurs and we see the requests show up normally in our pod logs.
```
$ oc logs dc/workshop
---> Running application from Python script (app.py) ...
 * Serving Flask app "app" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://0.0.0.0:8080/ (Press CTRL+C to quit)
10.129.0.1 - - [03/Apr/2020 17:00:07] "GET /5s_delay HTTP/1.1" 200 -
10.129.0.1 - - [03/Apr/2020 17:00:17] "GET /5s_delay HTTP/1.1" 200 -
```

## Next Steps
* Put some of what you've learned to use in a real OpenShift environment!
* If there are use cases you'd like covered here that aren't, open an issue to have them added!