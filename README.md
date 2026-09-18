# MakerWorld Library for Home Assistant

Read-only Home Assistant custom integration that synchronizes a MakerWorld collection and exposes one metadata sensor per model.

This integration synchronizes a MakerWorld collection and adds a one-click cloud print button for the preferred P2S profile. MakerWorld does not publish a supported public API, so all endpoint handling is isolated in `api.py`, errors are retried/contained, and no raw response, signed download URL, or access token is logged.

## Included metadata

- Collection model count and sync health
- Model title, cover image, numeric `design_id`, internal `model_id`, creator and source URL
- Compact print profile list with profile/instance ID, materials, AMS requirement, plates and estimated time
- Compatible printer names and P2S-specific compatibility/profile metadata when MakerWorld provides it
- A print button per model, using the preferred P2S profile and plate 1
- Automatic material-to-AMS-slot matching from `ha-bambulab` tray entities
- A fresh, short-lived MakerWorld cloud URL for every button press

## Installation

### Manual

1. Copy `custom_components/makerworld_library` to `<config>/custom_components/makerworld_library` on Home Assistant.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **MakerWorld Library**.
5. Keep the supplied values for Home Prints:
   - Collection ID: `35678497`
   - Collection path: `35678497-home-prints`
6. Select the cloud-connected P2S from the Bambu Lab integration.
7. Leave the token empty: the integration reuses the active `ha-bambulab` cloud token without copying it. Never enter a Bambu password.

The default poll interval is 45 minutes. It can be changed to 30–60 minutes through the integration's **Configure** button.

### HACS custom repository

1. In HACS, open **Integrations**.
2. Open the menu (three dots) and choose **Custom repositories**.
3. Add `https://github.com/Borratius/makerworld_library` as category **Integration**.
4. Search for **MakerWorld Library**, install it, and restart Home Assistant.

Then add **MakerWorld Library** under **Settings → Devices & services**. The defaults already point to the Home Prints collection.

## Entities

- `sensor.home_prints_models`: model count plus collection URL, last sync and partial failures.
- One sensor and one Print button per model. The sensor exposes metadata and the cover as `entity_picture`.

Newly added collection models are discovered on the next poll. Removed models become unavailable so Home Assistant history and entity-registry choices remain under user control.

## Access token handling

Public collection reads work without authentication. Cloud printing reuses the current bearer token held by the selected `ha-bambulab` config entry; it is read only when a print button is pressed and is never copied to entities, diagnostics, or logs. A manual token remains available as a fallback in the password-style field.

## Cloud print behavior

The button selects a P2S-compatible profile, requests a short-lived MakerWorld URL, matches every required material to a loaded AMS tray, and calls `bambu_lab.print_project_file`. It refuses to start when a required material is absent. Version 0.2 prints plate 1; models with multi-plate selection will be added after the P2S cloud path is verified on real hardware.

Recent Bambu firmware may reject third-party cloud write commands even while official Bambu Handy printing works. This integration reports that failure; it does not silently switch the printer to LAN mode or bypass Bambu authorization controls.

## API stability and logging

The integration uses community-observed, unsupported endpoints under `https://api.bambulab.com/v1/design-service`. MakerWorld can change these without notice. Temporary network/5xx/429 failures are retried. A failed collection request preserves the previous coordinator snapshot; a failed individual model-detail request still exposes summary metadata and logs a warning containing only the design ID and exception type.

Enable debug logging if troubleshooting is needed:

```yaml
logger:
  logs:
    custom_components.makerworld_library: debug
```

Do not post unredacted Home Assistant storage files when asking for support.
