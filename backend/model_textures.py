"""Safe, loss-aware GLB texture pack export and non-destructive replacement.

Operates on embedded PNG/JPEG images. Accessor, rig, animation and mesh data
remain byte-identical. WebP colour textures are encoded with Pillow and
referenced through the ratified EXT_texture_webp extension; material slots
for normals and ORM retain their existing textures. KTX2 uses optional tools.
"""
from __future__ import annotations
import base64
from hashlib import sha256
from binascii import Error as BinasciiError
from io import BytesIO
import json
import re
import struct
import zipfile
from PIL import Image, UnidentifiedImageError, features

MAX_GLB=100*1024*1024
MAX_PACK=56*1024*1024
MAX_TEXTURE=18*1024*1024
MAX_PIXELS=48_000_000
MAX_IMAGES=128
IMAGE_MIME={'image/png':'.png','image/jpeg':'.jpg'}
EXT_MIME={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}

class TextureError(ValueError):
    pass


def split_glb(data):
    if not 20<=len(data)<=MAX_GLB or data[:4]!=b'glTF':
        raise TextureError('Only embedded GLB 2.0 models up to 100 MB are supported')
    version,actual=struct.unpack_from('<II',data,4)
    if version!=2 or actual!=len(data):raise TextureError('Invalid GLB header')
    chunks=[];pos=12
    while pos+8<=len(data):
        length,kind=struct.unpack_from('<II',data,pos)
        if length%4 or pos+8+length>len(data):raise TextureError('Invalid GLB chunk length')
        chunks.append((kind,data[pos+8:pos+8+length]));pos+=8+length
    if pos!=len(data) or not chunks or chunks[0][0]!=0x4E4F534A:
        raise TextureError('Invalid GLB structure')
    try:document=json.loads(chunks[0][1].decode('utf-8').rstrip(' \x00'))
    except (UnicodeDecodeError,ValueError) as error:raise TextureError('Invalid GLB JSON') from error
    if not isinstance(document,dict) or not isinstance(document.get('asset'),dict) or not str(document['asset'].get('version','')).startswith('2.'):
        raise TextureError('Invalid glTF document')
    binaries=[c for c in chunks if c[0]==0x004E4942]
    binary=binaries[0][1] if binaries else b''
    return document,binary,chunks


def embedded_images(document,binary):
    images=document.get('images',[])
    if not isinstance(images,list):raise TextureError('Invalid image metadata')
    if len(images)>MAX_IMAGES:raise TextureError('Too many embedded textures')
    output=[]
    for i,image in enumerate(images):
        if 'bufferView' in image:
            try:
                view=document['bufferViews'][int(image['bufferView'])]
                if int(view.get('buffer',0))!=0:raise TextureError('Textures must use the primary GLB buffer')
                offset=int(view.get('byteOffset',0));length=int(view['byteLength'])
            except (KeyError,IndexError,ValueError,TypeError) as error:raise TextureError('Invalid texture bufferView') from error
            if offset<0 or length<=0 or length>MAX_TEXTURE or offset+length>len(binary):
                raise TextureError('Invalid texture data bounds')
            blob=binary[offset:offset+length]
        elif str(image.get('uri','')).startswith('data:'):
            try:
                uri=image['uri'];head,encoded=uri.split(',',1)
                if ';base64' not in head:raise ValueError('Non-base64 image URI')
                blob=base64.b64decode(encoded,validate=True)
            except (ValueError,TypeError,BinasciiError) as error:raise TextureError('Invalid embedded image URI') from error
        else:continue
        if len(blob)>MAX_TEXTURE:raise TextureError('Embedded texture exceeds the 18 MB limit')
        mime=image.get('mimeType') or ('image/png' if blob.startswith(b'\x89PNG') else 'image/jpeg' if blob.startswith(b'\xff\xd8') else '')
        if mime not in IMAGE_MIME:continue
        output.append((i,mime,blob))
    return output


def texture_archive(data):
    doc,binary,_=split_glb(data)
    items=embedded_images(doc,binary)
    if not items:raise TextureError('No editable embedded PNG/JPEG textures found')
    archive=BytesIO();manifest={'format':'UMI-GLB-TEXTURES-1','source_sha256':sha256(data).hexdigest(),'textures':[]}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as target:
        for index,mime,blob in items:
            name=f'texture-{index:04d}{IMAGE_MIME[mime]}'
            target.writestr(name,blob)
            manifest['textures'].append({'index':index,'file':name,'mime':mime,'sha256':sha256(blob).hexdigest()})
        target.writestr('manifest.json',json.dumps(manifest,indent=2))
        target.writestr('README.txt','Edit texture-NNNN.png/.jpg files using an image editor; keep the numeric index.\n'
                        'Reimport the ZIP into the exact source GLB on UMI LAB. Geometry stays untouched.\n'
                        'PNG/JPEG supported for direct replacement. WebP/KTX2 export needs glTF Transform.\n')
    return archive.getvalue()


def read_texture_archive(archive,source_data):
    if len(archive)>MAX_PACK:raise TextureError('Texture ZIP must be smaller than 56 MB')
    try:
        with zipfile.ZipFile(BytesIO(archive)) as z:
            if len(z.infolist())>MAX_IMAGES+10 or sum(i.file_size for i in z.infolist())>MAX_PACK:
                raise TextureError('Texture ZIP contains too much data')
            manifest=json.loads(z.read('manifest.json'))
            if not isinstance(manifest,dict):raise TextureError('Invalid texture pack manifest')
            if manifest.get('format')!='UMI-GLB-TEXTURES-1' or manifest.get('source_sha256')!=sha256(source_data).hexdigest():
                raise TextureError('This texture pack belongs to a different version of the model')
            entries={int(row['index']) for row in manifest.get('textures',[]) if isinstance(row,dict) and 'index' in row}
            replacements={}
            for item in z.infolist():
                if item.is_dir():continue
                if item.filename in ('manifest.json','README.txt'):continue
                match=re.fullmatch(r'texture-(\d{4})\.(png|jpg|jpeg)',item.filename,re.I)
                if not match or int(match.group(1)) not in entries or item.file_size>MAX_TEXTURE:
                    raise TextureError('Unknown image file in ZIP; use original texture-NNNN names')
                index=int(match.group(1));blob=z.read(item)
                replacements[index]=(EXT_MIME['.'+match.group(2).lower()],blob)
            if not replacements:raise TextureError('No PNG/JPEG texture replacements in ZIP')
            return replacements
    except (zipfile.BadZipFile,KeyError,ValueError,TypeError) as error:
        if isinstance(error,TextureError):raise
        raise TextureError('Invalid texture ZIP or manifest') from error


def _image_bytes(blob,divisor,format_name,scale=1.0,*,quality=85,png_compression=6,webp_effort=6,webp_lossless=False):
    try:
        with Image.open(BytesIO(blob)) as image:
            image.load()
            if image.width*image.height>MAX_PIXELS:raise TextureError('Texture exceeds 48 million pixels')
            if divisor>1 or scale<1:
                width=max(1,round(image.width*scale/divisor));height=max(1,round(image.height*scale/divisor))
                image=image.resize((width,height),Image.Resampling.LANCZOS)
            if format_name=='jpeg':
                if image.mode not in ('RGB','L'):image=image.convert('RGB')
                mime='image/jpeg';out=BytesIO();image.save(out,format='JPEG',quality=quality,optimize=True)
            elif format_name=='png':
                mime='image/png';out=BytesIO();image.save(out,format='PNG',compress_level=png_compression,optimize=False)
            elif format_name=='webp':
                if not features.check('webp'):
                    raise TextureError('Pillow WebP encoder is unavailable on this server')
                if image.mode not in ('RGB','RGBA'):
                    image=image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
                mime='image/webp';out=BytesIO();image.save(out,format='WEBP',quality=quality,method=webp_effort,lossless=webp_lossless)
            else:raise TextureError('Native texture pipeline supports PNG, JPEG or WebP')
            value=out.getvalue()
            if len(value)>MAX_TEXTURE:raise TextureError('Processed texture is too large')
            return mime,value
    except (UnidentifiedImageError,OSError,ValueError) as error:
        raise TextureError('Embedded texture cannot be decoded as PNG/JPEG') from error


def replace_glb_textures(data,*,divisor=1,texture_scale=1.0,texture_format='original',replacements=None,texture_quality=85,png_compression=6,webp_effort=6,webp_lossless=False):
    """Repack one GLB with updated embedded image bufferViews; never modify mesh payload bytes.

    BufferViews are reconstructed without changing geometry data, rigging, or
    animation payloads. A source with direct byte-offset meshopt extensions is
    refused rather than risking an invalid remapped compressed mesh.
    """
    if type(texture_quality) is not int or not 1<=texture_quality<=100:raise TextureError('Texture quality must be 1–100')
    if type(png_compression) is not int or not 0<=png_compression<=9:raise TextureError('PNG compression must be 0–9')
    if type(webp_effort) is not int or not 0<=webp_effort<=6:raise TextureError('WebP encoding effort must be 0–6')
    if type(webp_lossless) is not bool:raise TextureError('WebP lossless must be boolean')
    try:divisor=int(divisor)
    except (ValueError,TypeError) as error:raise TextureError('Texture factor must be 1, 2, 4, 8 or 16') from error
    if divisor not in (1,2,4,8,16):raise TextureError('Texture factor must be 1, 2, 4, 8 or 16')
    if texture_format not in ('original','png','jpeg','webp'):raise TextureError('Select Original, PNG, JPEG or WebP for native texture processing')
    try:texture_scale=float(texture_scale)
    except (TypeError,ValueError) as error:raise TextureError('Texture scale must be between 6.25% and 100%') from error
    if not .0625<=texture_scale<=1:raise TextureError('Texture scale must be between 6.25% and 100%')
    if replacements is None and divisor==1 and texture_scale==1 and texture_format=='original':return data
    doc,binary,chunks=split_glb(data)
    originals=embedded_images(doc,binary)
    if replacements is not None:
        available={i for i,_,_ in originals}
        if any(i not in available for i in replacements):raise TextureError('Texture index does not exist in this model')
    if not originals:raise TextureError('No editable embedded PNG/JPEG textures found')
    if 'EXT_meshopt_compression' in doc.get('extensionsUsed',[]):
        raise TextureError('Texture repacking of Meshopt-compressed GLBs requires glTF Transform')
    views=doc.get('bufferViews',[])
    view_payloads={i:binary[int(view.get('byteOffset',0)):int(view.get('byteOffset',0))+int(view['byteLength'])]
                   for i,view in enumerate(views) if int(view.get('buffer',0))==0}
    used_by_geometry=set()
    for accessor in doc.get('accessors',[]):
        if 'bufferView' in accessor:used_by_geometry.add(int(accessor['bufferView']))
        for field in ('indices','values'):
            sparse=accessor.get('sparse',{}).get(field,{})
            if isinstance(sparse,dict) and 'bufferView' in sparse:used_by_geometry.add(int(sparse['bufferView']))
    for mesh in doc.get('meshes',[]):
        for primitive in mesh.get('primitives',[]):
            draco=primitive.get('extensions',{}).get('KHR_draco_mesh_compression',{})
            if 'bufferView' in draco:used_by_geometry.add(int(draco['bufferView']))
    referenced_images={}
    for item in doc.get('images',[]):
        if 'bufferView' in item:
            view_id=int(item['bufferView']);referenced_images[view_id]=referenced_images.get(view_id,0)+1
    # EXT_texture_webp is a texture-level extension, not an image MIME override
    # in base glTF. Convert only colour/emissive slots, leaving normal/ORM maps
    # intact. Preserve original images when the same image is shared with a
    # non-colour texture or referenced by another feature.
    color_textures=set()
    for material in doc.get('materials',[]):
        for ref in (material.get('pbrMetallicRoughness',{}).get('baseColorTexture'),
                    material.get('emissiveTexture')):
            if isinstance(ref,dict) and isinstance(ref.get('index'),int):
                color_textures.add(ref['index'])
    if texture_format=='webp' and not color_textures and not doc.get('materials'):
        color_textures=set(range(len(doc.get('textures',[]))))
    color_images={doc['textures'][ti].get('source') for ti in color_textures
                  if ti<len(doc.get('textures',[]))}
    color_images.discard(None)
    webp_textures={}
    updated=0
    for index,mime,blob in originals:
        if texture_format=='webp' and index not in color_images:continue
        if replacements is not None and index not in replacements:continue
        if replacements is not None:
            mime,blob=replacements[index]
            if mime not in IMAGE_MIME:raise TextureError('Only PNG/JPEG replacements are supported')
        if divisor!=1 or texture_scale!=1 or texture_format!='original':
            mime,blob=_image_bytes(blob,divisor,texture_format if texture_format!='original' else ('png' if mime=='image/png' else 'jpeg'),texture_scale,quality=texture_quality,png_compression=png_compression,webp_effort=webp_effort,webp_lossless=webp_lossless)
        else:
            # Validate that reimported bytes really match their stated image format.
            with Image.open(BytesIO(blob)) as parsed:
                parsed.load()
                if parsed.width*parsed.height>MAX_PIXELS:raise TextureError('Texture exceeds 48 million pixels')
                actual='image/png' if parsed.format=='PNG' else 'image/jpeg' if parsed.format=='JPEG' else ''
                if actual!=mime:raise TextureError('Replacement extension does not match image data')
        old_view=doc['images'][index].get('bufferView')
        if texture_format=='webp':
            # Keep the PNG/JPEG image if any other slot shares it; this is
            # also safer for assets with materials outside the core schema.
            non_colour_uses=any(ti not in color_textures and tex.get('source')==index
                                for ti,tex in enumerate(doc.get('textures',[])))
            shared_view=old_view is not None and (int(old_view) in used_by_geometry or referenced_images.get(int(old_view),0)>1)
            if not non_colour_uses and not shared_view:
                # In-place WebP image replaces PNG/JPEG, avoiding duplicate
                # payload and delivering the expected file-size reduction.
                webp_index=index
                if old_view is None:
                    view_index=len(views)
                    views.append({'buffer':0,'byteOffset':0,'byteLength':len(blob)})
                else:view_index=int(old_view)
                view_payloads[view_index]=blob
                doc['images'][index].pop('uri',None)
                doc['images'][index]['bufferView']=view_index
                doc['images'][index]['mimeType']='image/webp'
            else:
                view_index=len(views)
                views.append({'buffer':0,'byteOffset':0,'byteLength':len(blob)})
                view_payloads[view_index]=blob
                webp_index=len(doc['images'])
                doc['images'].append({'bufferView':view_index,'mimeType':'image/webp'})
            for tex_id in color_textures:
                if tex_id<len(doc.get('textures',[])) and doc['textures'][tex_id].get('source')==index:
                    webp_textures[tex_id]=webp_index
            updated+=1
            continue
        if old_view is not None and (int(old_view) in used_by_geometry or referenced_images.get(int(old_view),0)>1):
            raise TextureError('Embedded texture shares a geometry/image bufferView; export it as a standalone texture first')
        if old_view is None:
            view_index=len(views)
            views.append({'buffer':0,'byteOffset':0,'byteLength':len(blob)})
        else:view_index=int(old_view)
        view_payloads[view_index]=blob
        doc['images'][index].pop('uri',None)
        doc['images'][index]['bufferView']=view_index
        doc['images'][index]['mimeType']=mime
        updated+=1
    if not updated:raise TextureError('No editable colour textures available for WebP encoding' if texture_format=='webp' else 'No textures replaced')
    if webp_textures:
        for tex_id,image_id in webp_textures.items():
            item=doc['textures'][tex_id]
            item.setdefault('extensions',{})['EXT_texture_webp']={'source':image_id}
            item.pop('source',None)
        doc.setdefault('extensionsUsed',[])
        if 'EXT_texture_webp' not in doc['extensionsUsed']:
            doc['extensionsUsed'].append('EXT_texture_webp')
        doc.setdefault('extensionsRequired',[])
        if 'EXT_texture_webp' not in doc['extensionsRequired']:
            doc['extensionsRequired'].append('EXT_texture_webp')
    new_binary=bytearray()
    for i,view in enumerate(views):
        if int(view.get('buffer',0))!=0:raise TextureError('Multi-buffer GLBs need conversion before texture repacking')
        if i not in view_payloads:raise TextureError('Invalid bufferView in model')
        payload=view_payloads[i]
        if len(payload)>MAX_GLB:raise TextureError('BufferView exceeds size limit')
        while len(new_binary)%4:new_binary.append(0)
        view['byteOffset']=len(new_binary)
        view['byteLength']=len(payload)
        new_binary.extend(payload)
    doc.setdefault('buffers',[{'byteLength':0}])[0]['byteLength']=len(new_binary)
    while len(new_binary)%4:new_binary.append(0)
    json_chunk=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    json_chunk+=b' '*((-len(json_chunk))%4)
    # Preserve any extension chunks other than old JSON/BIN.
    assembled=[(0x4E4F534A,json_chunk),(0x004E4942,bytes(new_binary))]+[(kind,chunk) for kind,chunk in chunks if kind not in (0x4E4F534A,0x004E4942)]
    length=12+sum(8+len(chunk) for _,chunk in assembled)
    if length>MAX_GLB:raise TextureError('Processed GLB exceeds 100 MB')
    stream=BytesIO();stream.write(struct.pack('<4sII',b'glTF',2,length))
    for kind,chunk in assembled:stream.write(struct.pack('<II',len(chunk),kind));stream.write(chunk)
    return stream.getvalue()
