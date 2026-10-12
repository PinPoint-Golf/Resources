# PinPoint Golf resources

Artwork and models made for [PinPoint Studio](https://github.com/PinPoint-Golf/PinPointStudio), kept here under the MIT licence so that other projects can use them.

| Folder | What it holds |
|---|---|
| [`clubheads/`](clubheads/) | Five parametric golf club heads (driver, 3 wood, hybrid, 7 iron, 56° wedge), built headless in Blender. Includes transparent renders in light, dark and line looks, plus JSON anchors for rotating them by face angle, path and loft. |
| [`ball/`](ball/) | A generic, unprinted golf ball (42.67 mm, 332 dimples in three sizes, dimple-free parting line), rendered in front, side and three-quarter views in light, dark and line looks, with JSON anchors for the pole axis and the parting line. Also the impact patch it leaves on face tape, as tintable SVG and PNG at 20, 25 and 30 mm contact diameters. |

Each folder holds its own generator source, its documentation and the outputs it produces, so you can use the renders as they are or rebuild them.

## Licence

Everything here is MIT (see [`LICENSE`](LICENSE)) unless a folder says otherwise. The third-party inputs are listed beside the files they cover. At present that is one CC0 HDRI in `clubheads/ref/` (see `SOURCE.txt`), which `ball/` also uses.

The models are generic. They contain no manufacturer geometry, artwork, names or logos.
