import os

import bpy
import mathutils
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
def getSkin(me, armob):
    pass

# Get animation
def getAnimation (obj):
    pass

# Add model to scene
def writeModel(scn, me, verts, faces):
    hasUv = bool(me.tessface_uv_textures)
    meshVerts = me.vertices
    nmodel = exporter.io_Model ()
    ngeom = exporter.io_Geometry ()
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
                fw ("Has animation")
                anim = getAnimation (ob)
            else:
                fw ("No animation")

            # Get mesh
            try:
                me = ob.to_mesh(scene, EXPORT_APPLY_MODIFIERS, 'PREVIEW')
            except:
                continue

            # Export skin
            armob = None
            if ob.parent and ob.parent.type == 'ARMATURE':
                armob = ob.parent

            vertices, faces = getGeometry (me)
            if armob:
                #skin, weights = getSkin (me, armob)
                pass

            writeModel (scn, me, vertices, faces)
        
        exp.write (filepath, scn)    
        file.close ()

    return {'FINISHED'}