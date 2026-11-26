# Windows Setup and access from phones

This guide covers releases that include Windows Setup and current development builds. Version v0.1.0 uses the source ZIP and serves its gallery on loopback.

## Install

Run the Windows x64 Setup and open FaceFlow from the Start menu. Setup includes Python, its dependencies, and the recognition models. FaceFlow opens the photographer view in your browser and leaves a console window open. Closing the window or pressing Ctrl+C stops the gallery.

The installer stores the app under `%LOCALAPPDATA%\Programs\FaceFlow` by default. It keeps gallery photos, indexes, and credentials in `%LOCALAPPDATA%\FaceFlow\data`. Uninstalling removes the app and leaves that data in place.

The legacy source ZIP keeps data under the extracted folder by default. To move it to Setup, back it up and copy it to the installed data path while all FaceFlow instances are closed. If the destination already contains a gallery, keep a separate backup of both directories before choosing which one to use. Windows Setup is currently unsigned.

## Share a published shoot on the local network

The photographer view listens on the host computer. In a published shoot, open **Доступ с телефона**, choose the IP of the host's local network, and select **Открыть доступ на 30 минут**. Copy the generated guest link and open it on a phone connected to the same trusted network.

The guest link serves one shoot. Guests can submit a selfie and view or download matches. To revoke access early, use **Закрыть доступ**, pause the shoot, or close FaceFlow. Photos and selfies travel over unencrypted HTTP, so only share on a trusted network.

Windows Firewall can block the temporary port. If Windows prompts for access, allow it for your trusted private network only. FaceFlow does not add firewall rules or change the Windows network profile. If guest Wi-Fi isolates devices, use a network where the phone can reach the host computer.
