# Third Party Licenses

This project uses the following third party libraries.

## Runtime Dependencies

| Package | Purpose | License | Notice |
| --- | --- | --- | --- |
| PySide6 | Python bindings for the Qt application framework | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, or commercial license | This application uses PySide6 / Qt. This project intends to use PySide6 under LGPLv3. |
| PySide6_Essentials | Qt for Python essential modules, installed as a PySide6 dependency | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, or commercial license | Distributed by the Qt for Python project. |
| PySide6_Addons | Qt for Python addon modules, installed as a PySide6 dependency | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, or commercial license | Distributed by the Qt for Python project. |
| shiboken6 | Python/C++ binding helper module, installed as a PySide6 dependency | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, or commercial license | Distributed by the Qt for Python project. |

The project dependency declaration is `PySide6>=6.5`; the exact installed versions may vary by environment.

## License Texts

- GNU Lesser General Public License v3.0: [licenses/LGPL-3.0.txt](licenses/LGPL-3.0.txt)
- GNU General Public License v3.0: [licenses/GPL-3.0.txt](licenses/GPL-3.0.txt)

LGPLv3 incorporates the terms of GPLv3 with additional permissions, so both texts are included.

## Qt / PySide6 Notice

pyTaskFlow uses PySide6, the official Python bindings for Qt. When distributing this application with PySide6 / Qt libraries, ensure that end users receive the applicable license texts and a prominent notice that the application uses PySide6 / Qt.

If you modify Qt, PySide6, or related LGPL-covered libraries, or distribute binaries with those libraries, review the LGPLv3 obligations for source availability, relinking/replacement, and installation information as applicable to your distribution format.
