bl_info = {
    "name": "Import Pokémon Masters Models",
    "author": "Turk, Jugolm, MiniEmerald",
    "version": (1, 3, 2),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "A tool designed to import LMD files from the mobile game Pokémon Masters",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

import bpy
import bmesh
import os
import io
import struct
import math
import mathutils
import numpy as np
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
from bpy_extras.io_utils import ImportHelper
import fnmatch
import traceback


# To find a file in a path (including subfolders). Thanks Nadia Alramli
# for the answer from some corner in StackOverflow a decade ago
def find_file(pattern, path):
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result


class PokeMasImport(bpy.types.Operator, ImportHelper):
    """Load a LMD file"""
    bl_idname = "import_scene.pokemonmasters"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ".wismda"
    filter_glob: StringProperty(
            default="*.lmd",
            options={'HIDDEN'},
    )

    filepath: StringProperty(subtype='FILE_PATH',)
    version: EnumProperty(name="Version", items=(("1.0","1.0","1.0"), ("1.2+","1.2+","1.2+")), default="1.2+")
    removedoubles: BoolProperty(name="Remove Doubles")
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    def draw(self, context):
        layout = self.layout
        layout.separator()
        layout.prop(self, 'version')
        #layout.separator()
        #layout.prop(self,'removedoubles')

    def execute(self, context):
        print("=====\nLoading file {}".format(self.filepath))

        f = open(self.filepath, "rb")
        f.seek(0x34)
        BoneDataOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        ArmatureObject = BuildSkeleton(f, BoneDataOffset)
        f.seek(0x38)
        MaterialDataOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        ParseMaterials(f, MaterialDataOffset)
        
        f.seek(0x48)
        MeshCount = int.from_bytes(f.read(4), byteorder='little')
        MeshList = []
        for x in range(MeshCount):
            MeshList.append(f.tell() + int.from_bytes(f.read(4), byteorder='little'))
        CurMeshOffset = f.tell()
        print("Loading meshes:")
        for x in MeshList:
            ReadMeshChunk(f, x, ArmatureObject, self.version, self.removedoubles)

        f.close()
        ArmatureObject.rotation_euler = (1.5707963705062866, 0, 0)
        return {'FINISHED'}
        
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def ReadMeshChunk(f, StartAddr, ArmatureObject, Version, RemoveDoubles=False):
    f.seek(StartAddr + 7)
    VertChunkSize = int.from_bytes(f.read(1), byteorder='little')
    
    f.seek(StartAddr + 0x8)
    ModelNameArea = f.tell() + int.from_bytes(f.read(4), byteorder='little')
    f.seek(ModelNameArea)
    ModelNameLength = int.from_bytes(f.read(4), byteorder='little')
    ModelName = f.read(ModelNameLength).decode('utf-8', 'replace')

    #Get Material Name
    f.seek(StartAddr + 0x14)
    MaterialNameOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
    f.seek(MaterialNameOffset + 8)
    MaterialNameSize = int.from_bytes(f.read(4), byteorder='little')
    MaterialNameText = f.read(MaterialNameSize).decode('utf-8', 'replace')
    
    f.seek(StartAddr + 0x58)
    WeightBoneNameTableStart = f.tell() + int.from_bytes(f.read(4), byteorder='little')
    
    f.seek(StartAddr + 0x5C)
    WeightBoneTableStart = f.tell() + int.from_bytes(f.read(4), byteorder='little')
    
    f.seek(StartAddr + 0x78)
    FaceCount = int.from_bytes(f.read(4), byteorder='little')
    f.seek(StartAddr + 0x84)
    VertCount = int.from_bytes(f.read(4), byteorder='little')
    SizeTest = VertCount * VertChunkSize
    if SizeTest < 0x100:
        Size = 1
    elif SizeTest < 0x10000:
        Size = 2
    else:
        Size = 4
    f.seek(8, 1)
    VertSize = int.from_bytes(f.read(Size), byteorder='little')
    VertOffset = f.tell()
    
    #Read Vert Info Here
    VertTable = []
    UVTable = []
    VGData = []
    ColorData = []
    AlphaData = []
    bHasColor = False
    for x in range(VertCount):
        TempVert = struct.unpack('fff', f.read(4*3))
        f.seek(4, 1)
        if (VertChunkSize >= 0x24) & (Version == "1.0"):
            bHasColor = True
            TempColor = struct.unpack('4B', f.read(4))
            ColorData.append((TempColor[0] / 255, TempColor[1] / 255, TempColor[2] / 255))
            AlphaData.append((TempColor[3] / 255, TempColor[3] / 255, TempColor[3] / 255))
        TempUV = (np.fromstring(f.read(2), dtype='<f2'), 1-np.fromstring(f.read(2), dtype='<f2'))
        if (VertChunkSize >= 0x24) & (Version == "1.0"):
            f.seek(VertChunkSize - 0x24, 1)
        VGBone = (
            int.from_bytes(f.read(1), byteorder='little'),
            int.from_bytes(f.read(1), byteorder='little'),
            int.from_bytes(f.read(1), byteorder='little'),
            int.from_bytes(f.read(1), byteorder='little')
        )
        if Version == "1.0":
            VGWeight = (
                int.from_bytes(f.read(2), byteorder='little') / 65535,
                int.from_bytes(f.read(2), byteorder='little') / 65535,
                int.from_bytes(f.read(2), byteorder='little') / 65535,
                int.from_bytes(f.read(2), byteorder='little') / 65535
            )
        else:
            VGWeight = struct.unpack('ffff', f.read(4 * 4))
        VGData.append((x, VGBone, VGWeight))
        VertTable.append(TempVert)
        UVTable.append(TempUV)
        
    if Size == 1: UnknownSize = 2
    else: UnknownSize = 4
    f.seek(VertOffset + VertSize + Size + UnknownSize)
    UnknownCount = int.from_bytes(f.read(4), byteorder='little')
    f.seek(0x10 * UnknownCount, 1)
    SizeTest = int.from_bytes(f.read(4), byteorder='little')
    if FaceCount < 0x100:
        Size = 1
    elif FaceCount < 0x10000:
        Size = 2
    else:
        Size = 4
    FaceSize = int.from_bytes(f.read(Size), byteorder='little')
    if VertCount < 0x100:
        FSize = 1
    elif VertCount < 0x10000:
        FSize = 2
    else:
        FSize = 4
    #FaceCount = int(FaceSize / FSize)
    FaceOffset = f.tell()
    
    #Read Faces
    FaceTable = []
    for x in range(0,FaceCount,3):
        FaceTable.append((
            int.from_bytes(f.read(FSize), byteorder='little'),
            int.from_bytes(f.read(FSize), byteorder='little'),
            int.from_bytes(f.read(FSize), byteorder='little')
        ))
        
    #GetWeight Paint Names
    WeightBoneTable = []
    f.seek(WeightBoneNameTableStart)
    WeightBoneCount = int.from_bytes(f.read(4), byteorder='little')

    for x in range(WeightBoneCount):
        f.seek(WeightBoneNameTableStart + x*4 + 4)
        WeightBoneNameOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        f.seek(WeightBoneNameOffset)
        WeightBoneNameSize = int.from_bytes(f.read(4), byteorder='little')
        WeightBoneName = f.read(WeightBoneNameSize).decode('utf-8', 'replace')
        WeightBoneTable.append(WeightBoneName)
        print('{}: {}'.format(WeightBoneName, WeightBoneNameOffset))
    
    #Build Mesh
    mesh1 = bpy.data.meshes.new("mesh")
    mesh1.use_auto_smooth = True
    obj = bpy.data.objects.new(ModelName, mesh1)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True) 
    mesh = bpy.context.object.data
    bm = bmesh.new()
    for v in VertTable:
        bm.verts.new((v[0], v[1], v[2]))
    vlist = [v for v in bm.verts]
    for face in FaceTable:
        try:
            bm.faces.new((vlist[face[0]], vlist[face[1]], vlist[face[2]]))
        except:
            continue
    print('- {}: {} - {}'.format(ModelName, MaterialNameText, len(vlist)))

    bm.to_mesh(mesh)

    uv_layer = bm.loops.layers.uv.verify()
    for face in bm.faces:
        face.smooth = True
        for l in face.loops:
            luv = l[uv_layer]
            try:
                luv.uv = UVTable[l.vert.index]
            except:
                continue
    bm.to_mesh(mesh)
    mesh.auto_smooth_angle = 1.2
    # if RemoveDoubles:
    #     bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00001)
    #     bm.to_mesh(mesh)
    #     mesh.validate(verbose=True)
    #     mesh.update()

    if bHasColor:
        color_layer = bm.loops.layers.color.new("Color")
        color_layerA = bm.loops.layers.color.new("Color_ALPHA")
        for face in bm.faces:
            for l in face.loops:
                l[color_layer] = ColorData[l.vert.index]
                l[color_layerA] = AlphaData[l.vert.index]
        bm.to_mesh(mesh)

    bm.free()

    #try vertex group creation
    for x in VGData:
        for i in range(4):
            if x[2][i] != 0:
                try:
                    if obj.vertex_groups.find(WeightBoneTable[x[1][i]]) == -1:
                        TempVG = obj.vertex_groups.new(name=WeightBoneTable[x[1][i]])
                    else:
                        TempVG = obj.vertex_groups[obj.vertex_groups.find(WeightBoneTable[x[1][i]])]
                    TempVG.add([x[0]], x[2][i], 'ADD')
                except Exception as e:
                    print(" WEIGHT FAIL")
                    raise e

    #add materials
    if obj.data.materials:
        obj.data.materials[0] = bpy.data.materials.get(MaterialNameText)
    else:
        obj.data.materials.append(bpy.data.materials.get(MaterialNameText))
    
    #add armature to mesh
    Arm = obj.modifiers.new("Armature", "ARMATURE")
    Arm.object = ArmatureObject
    obj.parent = ArmatureObject


def BuildSkeleton(f, DataStart):
    f.seek(DataStart + 8)
    BoneCount = int.from_bytes(f.read(4), byteorder='little')
    BoneOffsetTable = []
    for x in range(BoneCount):
        BoneOffsetTable.append(f.tell() + int.from_bytes(f.read(4), byteorder='little'))

    name = os.path.split(f.name)[-1]
    armature_data = bpy.data.armatures.new(name)
    armature_obj = bpy.data.objects.new(name, armature_data)
    bpy.context.scene.collection.objects.link(armature_obj)
    select_all(False)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    utils_set_mode('EDIT')
    
    BoneTable = {}
    for x in BoneOffsetTable:
        f.seek(x)
        Magic = int.from_bytes(f.read(4), byteorder='little')
        f.seek(x + 4)
        NameOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        f.seek(NameOffset)
        BoneNameLength = int.from_bytes(f.read(4), byteorder='little')
        BoneName = f.read(BoneNameLength).decode('utf-8', 'replace')
        f.seek(x + 8)
        BoneMatrix = mathutils.Matrix((
            struct.unpack('ffff', f.read(4 * 4)),
            struct.unpack('ffff', f.read(4 * 4)),
            struct.unpack('ffff', f.read(4 * 4)),
            struct.unpack('ffff', f.read(4 * 4))
        ))
        f.seek(x + 0x38)
        BonePos = struct.unpack('fff', f.read(4 * 3))
        f.seek(x + 0x48)
        BoneParentOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        f.seek(BoneParentOffset)
        BoneParentNameLength = int.from_bytes(f.read(4), byteorder='little')
        BoneParentName = f.read(BoneParentNameLength).decode('utf-8', 'replace')
        
        edit_bone = armature_obj.data.edit_bones.new(BoneName)
        edit_bone.use_connect = False
        edit_bone.use_inherit_rotation = True
        edit_bone.use_inherit_scale = True
        edit_bone.use_local_location = True
        edit_bone.head = (0, 0, 0)
        edit_bone.tail = (0, 0.05, 0)
        armature_obj.data.edit_bones.active = edit_bone
        BoneTable[BoneName] = {}
        BoneTable[BoneName]["Bone"] = edit_bone
        BoneTable[BoneName]["Parent"] = BoneParentName
        BoneTable[BoneName]["Position"] = BonePos
        BoneTable[BoneName]["Matrix"] = BoneMatrix
        BoneTable[BoneName]["Name"] = BoneName
        if Magic < 0x5000: continue
        edit_bone.parent = BoneTable[BoneParentName]["Bone"]
        #print(BoneName)
    
    bpy.context.view_layer.objects.active = armature_obj
    utils_set_mode("POSE")
    for x in BoneTable:
        pbone = armature_obj.pose.bones[x]
        pbone.rotation_mode = 'XYZ'
        TempRot = BoneTable[x]["Matrix"].to_euler()
        pbone.rotation_euler = (-TempRot[0], -TempRot[1], -TempRot[2])
        pbone.location = BoneTable[x]["Position"]
        bpy.ops.pose.armature_apply()
    
    utils_set_mode('OBJECT')
    return armature_obj


def ParseMaterials(f, DataStart):
    MatTable = []
    f.seek(DataStart + 4)
    MaterialNameOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
    f.seek(DataStart + 12)
    TextureCount = int.from_bytes(f.read(4), byteorder='little')
    TextureOffSetTable = []
    for x in range(TextureCount):
        TextureOffSetTable.append(f.tell() + int.from_bytes(f.read(4), byteorder='little'))
    Textures = {}
    print("Loading {} texture{}:".format(TextureCount, '' if TextureCount == 1 else 's'))
    for x in TextureOffSetTable:
        f.seek(x + 4)
        TexFileRefOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        TexFileNameOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        TexFileMapOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        f.seek(TexFileNameOffset)
        TexFileNameSize = int.from_bytes(f.read(4), byteorder='little')
        TexFileName = f.read(TexFileNameSize).decode('utf-8', 'replace')

        f.seek(TexFileRefOffset)
        TexFileRefSize = int.from_bytes(f.read(4), byteorder='little')
        TexFileRef = f.read(TexFileRefSize).decode('utf-8', 'replace')

        f.seek(TexFileMapOffset)
        TexFileMapSize = int.from_bytes(f.read(4), byteorder='little')
        TexFileMap = f.read(TexFileMapSize).decode('utf-8', 'replace')
        Textures.update({TexFileRef:TexFileName})
        tex = bpy.data.textures.get(TexFileName)
        if not tex:
            tex = bpy.data.textures.new(name=TexFileName,type='IMAGE')
            try:
                filepath = os.path.split(os.path.realpath(f.name))
                files = find_file(TexFileName, filepath[0])
                # Try finding the file by brute force
                if not files:
                    files = find_file(TexFileName.replace(".tga", ".ktx.tga"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga", ".png"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga", ".ktx.png"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga", "*.png"), filepath[0])
                if files:
                    bpy.ops.image.open(filepath=files[0])
                    filename = os.path.split(files[0])[-1]
                    tex.image = bpy.data.images.get(filename)
            except:
                print(traceback.format_exc())
        print("- {}: {} / {}".format(TexFileRef, TexFileName, TexFileMap))

    f.seek(MaterialNameOffset)
    MaterialCount = int.from_bytes(f.read(4), byteorder='little')
    print("Loading {} material{}:".format(MaterialCount, '' if MaterialCount == 1 else 's'))
    MatOffsetTable = []
    for x in range(MaterialCount):
        MatOffsetTable.append(f.tell() + int.from_bytes(f.read(4), byteorder='little'))
    for x in MatOffsetTable:
        f.seek(x + 4)
        MaterialNameTextOffset = f.tell() + int.from_bytes(f.read(4), byteorder='little')
        f.seek(MaterialNameTextOffset)
        MaterialNameTextSize = int.from_bytes(f.read(4), byteorder='little')
        MaterialNameText = f.read(MaterialNameTextSize).decode('utf-8', 'replace')

        f.seek(x + 0x38)
        flag = int.from_bytes(f.read(4), byteorder='little')
        if flag == 0x40000000:
            f.seek(x + 0x44)
        else:
            f.seek(x + 0x40)
        TexSlotCount = int.from_bytes(f.read(4), byteorder='little')
        TexSlotsOffset = []
        TexSlots = []
        print("- {}".format(MaterialNameText))

        for y in range(TexSlotCount):
            TexSlotsOffset.append(f.tell() + int.from_bytes(f.read(4), byteorder='little'))
        for texnode in TexSlotsOffset:
            f.seek(texnode)
            MaterialFileReferenceSize = int.from_bytes(f.read(4), byteorder='little')
            MaterialFileReferenceName = f.read(MaterialFileReferenceSize).decode('utf-8', 'replace')
            print('- Texture slot [{}]'.format(MaterialFileReferenceName))
            TexSlots.append(Textures.get(MaterialFileReferenceName))

        mat = bpy.data.materials.get(MaterialNameText)
        if mat == None:
            setupMaterialNodes(mat, MaterialNameText, TexSlots)

        MatTable.append(mat)

    return MatTable


def setupMaterialNodes(mat, MaterialNameText, TexSlots):
    mat = bpy.data.materials.new(name=MaterialNameText)
    mat.use_nodes = True
    mat.blend_method = 'HASHED'
    bsdf = mat.node_tree.nodes['Principled BSDF']
    for texture in TexSlots:
        tex = bpy.data.textures.get(texture)
        if tex and tex.image and 'Image Texture.001' not in mat.node_tree.nodes.keys():
            xRef, yRef = -500, 300
            texImageCo = mat.node_tree.nodes.new('ShaderNodeTexImage')
            texImageCo.image = bpy.data.images.load(tex.image.filepath)
            texImageCo.location = (xRef, yRef)

            texImageAo = mat.node_tree.nodes.new('ShaderNodeTexImage')
            texImageAo.image = bpy.data.images.load(tex.image.filepath.replace('_co.', '_ao.'))
            texImageAo.image.colorspace_settings.name = 'Non-Color'
            texImageAo.location = (xRef, 0)

            mixRGB = mat.node_tree.nodes.new('ShaderNodeMixRGB')
            mixRGB.blend_type = 'MULTIPLY'
            mixRGB.inputs['Fac'].default_value = .3
            mixRGB.location = (xRef + 330, yRef)

            mat.node_tree.links.new(texImageCo.outputs['Color'], mixRGB.inputs['Color1'])
            mat.node_tree.links.new(texImageCo.outputs['Alpha'], bsdf.inputs['Alpha'])
            mat.node_tree.links.new(texImageAo.outputs['Color'], mixRGB.inputs['Color2'])
            mat.node_tree.links.new(texImageAo.outputs['Alpha'], bsdf.inputs['Specular'])
            mat.node_tree.links.new(mixRGB.outputs['Color'], bsdf.inputs['Base Color'])

            if MaterialNameText.endswith("face"):
                mappingCo = mat.node_tree.nodes.new('ShaderNodeMapping')
                mappingCo.location = (xRef - 400, yRef)

                mappingAo = mat.node_tree.nodes.new('ShaderNodeMapping')
                mappingAo.location = (xRef - 400, -80)
                try:
                    mappingAo.inputs['Scale'].default_value = (4, 4, 1)
                except KeyError:
                    mappingAo.scale = (4, 4, 1)
                    mappingAo.location[1] = 0

                texCoord = mat.node_tree.nodes.new('ShaderNodeTexCoord')
                texCoord.location = (xRef - 600, yRef - 180)

                mat.node_tree.links.new(mappingCo.outputs['Vector'], texImageCo.inputs['Vector'])
                mat.node_tree.links.new(mappingAo.outputs['Vector'], texImageAo.inputs['Vector'])
                mat.node_tree.links.new(texCoord.outputs['UV'], mappingCo.inputs['Vector'])
                mat.node_tree.links.new(texCoord.outputs['UV'], mappingAo.inputs['Vector'])


def select_all(select):
    if select:
        actionString = 'SELECT'
    else:
        actionString = 'DESELECT'

    if bpy.ops.object.select_all.poll():
        bpy.ops.object.select_all(action=actionString)

    if bpy.ops.mesh.select_all.poll():
        bpy.ops.mesh.select_all(action=actionString)

    if bpy.ops.pose.select_all.poll():
        bpy.ops.pose.select_all(action=actionString)


def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)


def menu_func_import(self, context):
    self.layout.operator(PokeMasImport.bl_idname, text="Pokémon Masters (.lmd)")


def register():
    bpy.utils.register_class(PokeMasImport)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(PokeMasImport)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
       

if __name__ == "__main__":
    register()
