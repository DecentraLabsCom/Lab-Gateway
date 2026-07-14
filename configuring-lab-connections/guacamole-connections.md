# Guacamole Connections

Access http(s)://labgatewayURL/guacamole and log in to guacamole using the admin username and password you configured during the installation of the Lab Gateway.

```mermaid
flowchart LR
    Admin["Gateway admin"] --> Guac["Guacamole admin UI"]
    Guac --> Conn["Create RDP connection"]
    Conn --> Station["Windows lab computer"]
    Conn --> Selector["Connection ID"]
    Selector --> LabManager["Lab Manager"]
    LabManager --> Chain["Published lab accessKey = guac:id:<id>"]
```

<figure><img src="../.gitbook/assets/image (2).png" alt=""><figcaption></figcaption></figure>

After that, go to Settings on the top right.\

When the connection is saved, record its numeric Guacamole connection ID. A
physical lab published on chain must use `accessKey=guac:id:<connection_id>`.
Set `accessURI` to the public origin of the Gateway that owns this Guacamole
catalog. In a Full + N Lite or standalone-backend + N Lite deployment, the
control-plane backend uses that origin to select the explicit remote
provisioner route; it must not fall back to another Gateway's local catalog.


<figure><img src="../.gitbook/assets/image (4).png" alt=""><figcaption></figcaption></figure>

Then go to Connections and click on the "New Connection" button to configure a new connection to your lab computer.

<figure><img src="../.gitbook/assets/image (5).png" alt=""><figcaption></figcaption></figure>

There, you must setup a few things:

* **Name:** This is just the name by which the connection will be displayed in the Guacamole list.
* **Protocol:** Should be set to "RDP" (Windows' Remote Desktop Protocol).
* **Network:**
  * _Hostname:_ Lab computer's IP.
  * _Port:_ This must be set to "3389" for RDP connections to work.
* **Authentication**
  * _Username:_ Windows account username. This is the Windows account your lab users will use when accessing your computer.
  * _Password:_ The password for the above user account.
  * _Security mode:_ Should be set to "Any".
  * _Ignore server certificate:_ Should be checked.
* **Remote App**
  * _Program:_ This should be filled with the name of the DecentraLabs' Lab Station .exe file (e.g. `AppControl.exe`).
  * _Working directory:_ The path to where the Lab Station executables are located in your Windows system.
  * _Parameters:_ These are inline parameters passed to AppControl.exe and to your lab app. For the first ones, there are two required: the lab app's window class and the lab app's path in your system. To learn how to obtain the window class of your lab app and what other parameters you can use, read the documentation in Lab Station. For the second ones (parameters to be passed to your lab app), those are dependant to the program you will be running. You can find more details on this in the Lab Station documentation too.

The image below shows the full set of parameters configured for a lab connection.

<figure><img src="../.gitbook/assets/Guacamole_NewConnection.png" alt=""><figcaption></figcaption></figure>
