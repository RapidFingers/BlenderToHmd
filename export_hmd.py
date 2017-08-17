import os

import math
import bpy
import mathutils
from mathutils import Vector, Matrix
import bpy_extras.io_utils
from . import exporter

from progress_report import ProgressReport, ProgressReportSubstep

# Round vector2
def rvec2d(v):
    return round(v[0], 4), round(v[1], 4)

# Round vector3
def rvec3d(v):
    return round(v[0], 4), round(v[1], 4), round(v[2], 4)

# Triangulate mesh
def meshTriangulate(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()

# Get vertices and faces from mesh   
def getGeometry (me):
    meshTriangulate (me)
    me.calc_tessface ()
    me.calc_normals ()
    meshVerts = me.vertices

    # vdict = {} # (index, normal, uv) -> new index
    vdict = [{} for i in range(len(meshVerts))]
    normal = normalKey = uvcoord = uvcoordKey = None
    vertCount = 0
    vertArray = []
    faces = [[] for f in range(len(me.tessfaces))]

    hasUv = bool(me.tessface_uv_textures)
    if hasUv:
        uvLayer = me.tessface_uv_textures.active.data

    for ti, f in enumerate(me.tessfaces):
        # Normals
        #normal = f.normal[:]
        #normalKey = rvec3d(normal)

        if hasUv:
            uv = uvLayer[ti]
            uv = uv.uv1, uv.uv2, uv.uv3, uv.uv4

        faceVerts = f.vertices
        pf = faces[ti]

        for j, vidx in enumerate(faceVerts):
            vert = meshVerts[vidx]

            # Normals
            normal = vert.normal[:]
            normalKey = rvec3d(normal)

            if hasUv:
                uvcoord = uv[j][0], uv[j][1]
                uvcoordKey = rvec2d(uvcoord)

            key = normalKey, uvcoordKey

            vdictLocal = vdict[vidx]
            pfVidx = vdictLocal.get(key)

            if pfVidx is None:
                pfVidx = vdictLocal[key] = vertCount
                vertArray.append((vidx, normal, uvcoord))
                vertCount += 1
            
            pf.append(pfVidx)

    return vertArray, faces

# Get armature and weights
def getSkin(ob, me, armob, fw):
    skin = exporter.io_Skin ()

    loc, rot, scale = armob.matrix_local.decompose()

    meshVerts = me.vertices
    
    arm = armob.data
    vertexGroups = ob.vertex_groups
    bones = arm.bones
    poseBones = armob.pose.bones

    boneDict = {}

    ind = 0
    for bone in bones:
        bdat = { "index" : ind, "parent" : None }         
        if bone.parent:
            bdat["parent"] = bone.parent.name
        
        boneDict[bone.name] = bdat
        ind += 1

    for name in boneDict:
        boneData = boneDict[name]
        parName = boneData["parent"]
        poseBone = poseBones[name]
        poseBoneMat = poseBone.bone.matrix_local

        loc, rot, scale = poseBoneMat.decompose()
        joint = exporter.io_Joint ()
        joint.index = boneData["index"]
        joint.name = name
        joint.setPosition (loc.x, loc.y, loc.z)

        parInd = 0
        if parName:
            parBoneData = boneDict[parName]
            parInd = parBoneData["index"]            
        
        joint.parentIndex = parInd
        skin.addJoint (joint)

        #loc, rot, scale = poseBoneMat.decompose()
        #if parName:
        #    pass
    
    # weights    
    weightDict = None
    if len (vertexGroups) > 0:
        groupDict = {}
        bonePerVertex = 1
        for vg in vertexGroups:
            boneDat = boneDict[vg.name]
            groupDict[vg.index] = boneDat["index"]

        weightDict = {}
        for vert in meshVerts:
            vertWeights = []
            for vg in vert.groups:
                boneIndex = groupDict[vg.group]
                vertWeights.append ( { "boneIndex" : boneIndex, "weight" : vg.weight } )

            wLen = len (vertWeights)
            if (wLen > bonePerVertex):
                bonePerVertex = wLen

            weightDict[vert.index] = vertWeights
        
        skin.bonePerVertex = bonePerVertex

    return (skin, weightDict)

# Get animation
def getAnimation (obj, anim, fw):
    fw (obj.name)

# Add model to scene
def writeModel(scn, ob, me, verts, faces, weights, skin):
    hasUv = bool(me.tessface_uv_textures)
    meshVerts = me.vertices
    nmodel = exporter.io_Model ()
    nmodel.name = ob.name
    nmodel.skin = skin    
    ngeom = exporter.io_Geometry ()
    ngeom.hasWeights = weights != None
    ngeom.hasUv = hasUv
    for i, v in enumerate(verts):
        pos = rvec3d (meshVerts[v[0]].co[:])
        nor = rvec3d (v[1])
        vert = exporter.io_Vertex ()
        vert.setPosition (pos[0], pos[1], pos[2])
        vert.setNormal (nor[0], nor[1], nor[2])
        if hasUv:
            uv = rvec2d (v[2])
            vert.setUv (uv[0], 1 - uv[1])

        if weights:
            wList = weights[v[0]]            
            for ind in range (0, 4):
                if (len (wList) > ind):
                    wData = wList[ind]
                    weight = wData["weight"]
                    boneIndex = wData["boneIndex"]
                    vert.addWeight (weight, boneIndex)
                else:
                    vert.addWeight (0, 0)

        ngeom.addVertex (vert)

    for pf in faces:
        ngeom.addIndex (pf[0])
        ngeom.addIndex (pf[1])
        ngeom.addIndex (pf[2])    

    nmodel.geometry = ngeom
    scn.addModel (nmodel)

# Save scene to HMD
def save(context, filepath,
        EXPORT_APPLY_MODIFIERS = True):
    with ProgressReport(context.window_manager) as progress:
        scene = context.scene
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
        
        frame = scene.frame_current
        scene.frame_set(frame, 0.0)
        objects = scene.objects

        nscene = exporter.io_Scene ()
        file = open(filepath + ".log", 'w')
        fw = file.write

        exp = exporter.io_Exporter ()
        scn = exporter.io_Scene ()

        for oi, ob in enumerate(objects):
            # Animation export
            if ob.animation_data:
                anim = getAnimation (ob, ob.animation_data, fw)            

            # Get mesh
            try:
                me = ob.to_mesh(scene, EXPORT_APPLY_MODIFIERS, 'PREVIEW')
            except:
                continue

            vertices, faces = getGeometry (me)

            # Export skin
            armob = None
            skin = None
            weights = None
            if ob.parent and ob.parent.type == 'ARMATURE':
                armob = ob.parent
                skin, weights = getSkin (ob, me, armob, fw)

            writeModel (scn, ob, me, vertices, faces, weights, skin)
        
        exp.write (filepath, scn)    
        file.close ()

    return {'FINISHED'}