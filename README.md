# PokemonMasters
Blender 2.80+ import script for LMD files from Pokemon Masters

Just place it in your Blender install's addons folder and enable it in the preferences.

This fork adds some transparency sets and tries to detect and import textures.


## Mini-FAQ

##### The texture looks weird/noisy on some objects (Ex : Caitlyn/ch0095_00_cattleya's mantle)
Select the object, open the material tab, go down to Settings and change "Blend Mode" from Alpha Hashed to Alpha Blend.

##### How do I change the characters' expressions?
Edit the Location X and/or Location Y of the top Mapping node.
Valid values are 0, 0.25, 0.5 and 0.75 for both Location X and Y.


## Credits
- Turk645 : Original version of the plugin
- Jugolm : 1.2+ model support, automatic texture importing
