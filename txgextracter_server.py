import os
import sys

target_dir = "/data/alg/tcg/PaddleDetection-release-2.6/deploy/python"
sys.path.append(target_dir)
import fitz
from bs4 import BeautifulSoup
from PIL import Image
from paddle.vision.transforms import Compose, ToTensor
import yaml
import json
import cv2
import numpy as np
import paddle
from paddle.inference import Config
from paddle.inference import create_predictor
from preprocess import preprocess, Resize, NormalizeImage, Permute, PadStride, LetterBoxResize, WarpAffine, Pad, \
    decode_image
from utils import argsparser, Timer, multiclass_nms, coco_clsid2catid
from flask import Flask, request, jsonify

app = Flask(__name__)

keywords = ['应用原理图', '典型应用电路', '应用实例和使用上注意事项', '典型应用', '典型应用图',
            'TYPICAL APPLICATION CIRCUIT', 'STANDARD CONNECTION DIAGRAM', 'STANDARD CONNECTION CIRCUIT',
            'TYPICAL CONNECTION DIAGRAM', 'SIMPLIFIED APPLICATION CIRCUIT', 'TYPICAL APPLICATIONS CIRCUIT',
            'TYPICAL OPERATING CIRCUIT', 'APPLICATION INFORMATION', 'TYPICAL APPLICATIONS', 'TYPICAL APPLICATION',
            'APPLICATION NOTES', 'APPLICATIONS INFORMATION', 'APPLICATION CIRCUIT', 'STANDARD USAGE', 'EASY USAGE',
            'STANDARD METHOD', 'RECOMMENDED CIRCUIT', 'APPLICATION SCHEMATIC', '[APPLICATION]', 'APPLICATION DIAGRAM',
            'STANDARD APPLICATION', 'APPLICATION EXAMPLE']
keywords += ['FUNCTIONAL DIAGRAM', 'Simplified Schematic']
titlekeywords = ['FEATURES']
labelnames = ['figure', 'equation', 'table']
vis = 0
colormap = [(0, 255, 255), (0, 255, 0), (0, 0, 255)]
SUPPORT_MODELS = {
    'YOLO', 'PPYOLOE', 'RCNN', 'SSD', 'Face', 'FCOS', 'SOLOv2', 'TTFNet',
    'S2ANet', 'JDE', 'FairMOT', 'DeepSORT', 'GFL', 'PicoDet', 'CenterNet',
    'TOOD', 'RetinaNet', 'StrongBaseline', 'STGCN', 'YOLOX', 'YOLOF', 'PPHGNet',
    'PPLCNet', 'DETR', 'CenterTrack'
}
parent_path = os.path.abspath(os.path.join(__file__, *(['..'])))
sys.path.insert(0, parent_path)
paddle.enable_static()
detector_func = 'Detector'
model_dir = '/data/alg/tcg/PaddleDetection-release-2.6/coarse_inference_model/ppyoloe_plus_crn_x_80e_coco'  # 'backup1model/coarse_inference_model/ppyoloe_plus_crn_x_80e_coco'
output_dir = 'infer_output'
model_dir1 = '/data/alg/tcg/PaddleDetection-release-2.6/fine_inference_model/ppyoloe_plus_crn_x_80e_coco'
output_dir1 = 'infer_output'
threshold = 0.45
slice_size = [2200, 2200]
overlap_ratio = [0.5, 0.5]
combine_method = 'nms'
match_threshold = 0.2
match_metric = 'ios'
device = 'GPU'
run_mode = 'paddle'
batch_size = 1
trt_min_shape = 1
trt_max_shape = 1280
trt_opt_shape = 640
trt_calib_mode = False
cpu_threads = 1
enable_mkldnn = False
enable_mkldnn_bfloat16 = False
save_images = True
save_results = True


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(NpEncoder, self).default(obj)


def pd_tensor2img(img):
    img = paddle.clip(img * 255, 0, 255)
    img = paddle.round(img)
    img = img[0].transpose((1, 2, 0))
    img = img[:, :, ::-1].astype('uint8')
    img = img.numpy()
    return img


def sdnms(rawdets, appendscore='no', match_threshold=0.2, match_metric='ios', nmsthr=0.45):
    """ Apply NMS to avoid detecting too many overlapping bounding boxes.
        Args:
            dets: shape [N, 5], [score, x1, y1, x2, y2]
            match_metric: 'iou' or 'ios'
            match_threshold: overlap thresh for match metric.
    """
    if appendscore == 'no':
        appendscore = np.zeros((len(rawdets)))
    nmsthrlist = [0.6, 0.6, 0.6]
    dets = rawdets[:, 1:]
    if dets.shape[0] == 0:
        return dets[[], :]
    scores = dets[:, 0]
    x1 = dets[:, 1]
    y1 = dets[:, 2]
    x2 = dets[:, 3]
    y2 = dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    ndets = dets.shape[0]
    suppressed = np.zeros((ndets), dtype=np.int32)

    for _i in range(ndets):
        i = order[_i]
        nmsthr = nmsthrlist[int(rawdets[i, 0])] - appendscore[i]
        if dets[i, 0] < nmsthr:
            suppressed[i] = 1
        if suppressed[i] == 1:
            continue
        ix1 = x1[i]
        iy1 = y1[i]
        ix2 = x2[i]
        iy2 = y2[i]
        iarea = areas[i]
        for _j in range(_i + 1, ndets):
            j = order[_j]
            nmsthr = nmsthrlist[int(rawdets[j, 0])] - appendscore[j]
            if dets[j, 0] < nmsthr:
                suppressed[j] = 1
            if suppressed[j] == 1:
                continue
            xx1 = max(ix1, x1[j])
            yy1 = max(iy1, y1[j])
            xx2 = min(ix2, x2[j])
            yy2 = min(iy2, y2[j])
            w = max(0.0, xx2 - xx1 + 1)
            h = max(0.0, yy2 - yy1 + 1)
            inter = w * h
            if match_metric == 'iou':
                union = iarea + areas[j] - inter
                match_value = inter / union
            elif match_metric == 'ios':
                smaller = min(iarea, areas[j])
                match_value = inter / smaller
            else:
                raise ValueError()
            if match_value >= match_threshold:
                suppressed[j] = 1
    keep = np.where(suppressed == 0)[0]
    rawdets[:, 1] = rawdets[:, 1] + appendscore
    dets = rawdets[keep, :]
    return dets


class Detector(object):
    """
    Args:
        pred_config (object): config of model, defined by `Config(model_dir)`
        model_dir (str): root path of model.pdiparams, model.pdmodel and infer_cfg.yml
        device (str): Choose the device you want to run, it can be: CPU/GPU/XPU, default is CPU
        run_mode (str): mode of running(paddle/trt_fp32/trt_fp16)
        batch_size (int): size of pre batch in inference
        trt_min_shape (int): min shape for dynamic shape in trt
        trt_max_shape (int): max shape for dynamic shape in trt
        trt_opt_shape (int): opt shape for dynamic shape in trt
        trt_calib_mode (bool): If the model is produced by TRT offline quantitative
            calibration, trt_calib_mode need to set True
        cpu_threads (int): cpu threads
        enable_mkldnn (bool): whether to open MKLDNN
        enable_mkldnn_bfloat16 (bool): whether to turn on mkldnn bfloat16
        output_dir (str): The path of output
        threshold (float): The threshold of score for visualization
        delete_shuffle_pass (bool): whether to remove shuffle_channel_detect_pass in TensorRT.
                                    Used by action model.
    """

    def __init__(self,
                 model_dir,
                 device='CPU',
                 run_mode='paddle',
                 batch_size=1,
                 trt_min_shape=1,
                 trt_max_shape=1280,
                 trt_opt_shape=640,
                 trt_calib_mode=False,
                 cpu_threads=1,
                 enable_mkldnn=False,
                 enable_mkldnn_bfloat16=False,
                 output_dir='output',
                 threshold=0.5,
                 delete_shuffle_pass=False):
        self.pred_config = self.set_config(model_dir)
        self.predictor, self.config = load_predictor(
            model_dir,
            self.pred_config.arch,
            run_mode=run_mode,
            batch_size=batch_size,
            min_subgraph_size=self.pred_config.min_subgraph_size,
            device=device,
            use_dynamic_shape=self.pred_config.use_dynamic_shape,
            trt_min_shape=trt_min_shape,
            trt_max_shape=trt_max_shape,
            trt_opt_shape=trt_opt_shape,
            trt_calib_mode=trt_calib_mode,
            cpu_threads=cpu_threads,
            enable_mkldnn=enable_mkldnn,
            enable_mkldnn_bfloat16=enable_mkldnn_bfloat16,
            delete_shuffle_pass=delete_shuffle_pass)
        self.det_times = Timer()
        self.cpu_mem, self.gpu_mem, self.gpu_util = 0, 0, 0
        self.batch_size = batch_size
        self.output_dir = output_dir
        self.threshold = threshold

    def set_config(self, model_dir):
        return PredictConfig(model_dir)

    def preprocess(self, image_list):
        preprocess_ops = []
        for op_info in self.pred_config.preprocess_infos:
            new_op_info = op_info.copy()
            op_type = new_op_info.pop('type')
            preprocess_ops.append(eval(op_type)(**new_op_info))

        input_im_lst = []
        input_im_info_lst = []
        for im_path in image_list:
            im, im_info = preprocess(im_path, preprocess_ops)
            input_im_lst.append(im)
            input_im_info_lst.append(im_info)
        inputs = create_inputs(input_im_lst, input_im_info_lst)
        input_names = self.predictor.get_input_names()
        for i in range(len(input_names)):
            input_tensor = self.predictor.get_input_handle(input_names[i])
            if input_names[i] == 'x':
                input_tensor.copy_from_cpu(inputs['image'])
            else:
                input_tensor.copy_from_cpu(inputs[input_names[i]])

        return inputs

    def postprocess(self, inputs, result):
        # postprocess output of predictor
        np_boxes_num = result['boxes_num']
        assert isinstance(np_boxes_num, np.ndarray), \
            '`np_boxes_num` should be a `numpy.ndarray`'

        result = {k: v for k, v in result.items() if v is not None}
        return result

    def predict(self, repeats=1, run_benchmark=False):
        '''
        Args:
            repeats (int): repeats number for prediction
        Returns:
            result (dict): include 'boxes': np.ndarray: shape:[N,6], N: number of box,
                            matix element:[class, score, x_min, y_min, x_max, y_max]
                            MaskRCNN's result include 'masks': np.ndarray:
                            shape: [N, im_h, im_w]
        '''
        # model prediction
        np_boxes_num, np_boxes, np_masks = np.array([0]), None, None

        if run_benchmark:
            for i in range(repeats):
                self.predictor.run()
                paddle.device.cuda.synchronize()
            result = dict(
                boxes=np_boxes, masks=np_masks, boxes_num=np_boxes_num)
            return result

        for i in range(repeats):
            self.predictor.run()
            output_names = self.predictor.get_output_names()
            boxes_tensor = self.predictor.get_output_handle(output_names[0])
            np_boxes = boxes_tensor.copy_to_cpu()
            if len(output_names) == 1:
                # some exported model can not get tensor 'bbox_num'
                np_boxes_num = np.array([len(np_boxes)])
            else:
                boxes_num = self.predictor.get_output_handle(output_names[1])
                np_boxes_num = boxes_num.copy_to_cpu()
            if self.pred_config.mask:
                masks_tensor = self.predictor.get_output_handle(output_names[2])
                np_masks = masks_tensor.copy_to_cpu()
        result = dict(boxes=np_boxes, masks=np_masks, boxes_num=np_boxes_num)
        return result

    def get_timer(self):
        return self.det_times

    def predict_image(self, imglist):
        # slice infer only support bs=1
        results = []
        for i in range(len(imglist)):
            rawimg = cv2.cvtColor(imglist[i], cv2.COLOR_BGR2RGB)

            batch_image_list = [rawimg]
            inputs = self.preprocess(batch_image_list)
            result = self.predict()
            result = self.postprocess(inputs, result)
            st, ed = 0, result['boxes_num'][0]  # start_index, end_index:
            boxes_num = result['boxes_num'][0]
            ed = st + boxes_num
            r = sdnms(result['boxes'][st:ed])
            results.append(r)
        return results


def create_inputs(imgs, im_info):
    """generate input for different model type
    Args:
        imgs (list(numpy)): list of images (np.ndarray)
        im_info (list(dict)): list of image info
    Returns:
        inputs (dict): input of model
    """
    inputs = {}

    im_shape = []
    scale_factor = []
    if len(imgs) == 1:
        inputs['image'] = np.array((imgs[0],)).astype('float32')
        inputs['im_shape'] = np.array(
            (im_info[0]['im_shape'],)).astype('float32')
        inputs['scale_factor'] = np.array(
            (im_info[0]['scale_factor'],)).astype('float32')
        return inputs

    for e in im_info:
        im_shape.append(np.array((e['im_shape'],)).astype('float32'))
        scale_factor.append(np.array((e['scale_factor'],)).astype('float32'))

    inputs['im_shape'] = np.concatenate(im_shape, axis=0)
    inputs['scale_factor'] = np.concatenate(scale_factor, axis=0)

    imgs_shape = [[e.shape[1], e.shape[2]] for e in imgs]
    max_shape_h = max([e[0] for e in imgs_shape])
    max_shape_w = max([e[1] for e in imgs_shape])
    padding_imgs = []
    for img in imgs:
        im_c, im_h, im_w = img.shape[:]
        padding_im = np.zeros(
            (im_c, max_shape_h, max_shape_w), dtype=np.float32)
        padding_im[:, :im_h, :im_w] = img
        padding_imgs.append(padding_im)
    inputs['image'] = np.stack(padding_imgs, axis=0)
    return inputs


class PredictConfig():
    """set config of preprocess, postprocess and visualize
    Args:
        model_dir (str): root path of model.yml
    """

    def __init__(self, model_dir):
        # parsing Yaml config for Preprocess
        deploy_file = os.path.join(model_dir, 'infer_cfg.yml')
        with open(deploy_file) as f:
            yml_conf = yaml.safe_load(f)
        self.check_model(yml_conf)
        self.arch = yml_conf['arch']
        self.preprocess_infos = yml_conf['Preprocess']
        self.min_subgraph_size = yml_conf['min_subgraph_size']
        self.labels = yml_conf['label_list']
        self.mask = False
        self.use_dynamic_shape = yml_conf['use_dynamic_shape']
        if 'mask' in yml_conf:
            self.mask = yml_conf['mask']
        self.tracker = None
        if 'tracker' in yml_conf:
            self.tracker = yml_conf['tracker']
        if 'NMS' in yml_conf:
            self.nms = yml_conf['NMS']
        if 'fpn_stride' in yml_conf:
            self.fpn_stride = yml_conf['fpn_stride']
        if self.arch == 'RCNN' and yml_conf.get('export_onnx', False):
            print(
                'The RCNN export model is used for ONNX and it only supports batch_size = 1'
            )
        self.print_config()

    def check_model(self, yml_conf):
        """
        Raises:
            ValueError: loaded model not in supported model type
        """
        for support_model in SUPPORT_MODELS:
            if support_model in yml_conf['arch']:
                return True
        raise ValueError("Unsupported arch: {}, expect {}".format(yml_conf[
                                                                      'arch'], SUPPORT_MODELS))

    def print_config(self):
        print('-----------  Model Configuration -----------')
        print('%s: %s' % ('Model Arch', self.arch))
        print('%s: ' % ('Transform Order'))
        for op_info in self.preprocess_infos:
            print('--%s: %s' % ('transform op', op_info['type']))
        print('--------------------------------------------')


def load_predictor(model_dir,
                   arch,
                   run_mode='paddle',
                   batch_size=1,
                   device='CPU',
                   min_subgraph_size=3,
                   use_dynamic_shape=False,
                   trt_min_shape=1,
                   trt_max_shape=1280,
                   trt_opt_shape=640,
                   trt_calib_mode=False,
                   cpu_threads=1,
                   enable_mkldnn=False,
                   enable_mkldnn_bfloat16=False,
                   delete_shuffle_pass=False):
    """set AnalysisConfig, generate AnalysisPredictor
    Args:
        model_dir (str): root path of __model__ and __params__
        device (str): Choose the device you want to run, it can be: CPU/GPU/XPU, default is CPU
        run_mode (str): mode of running(paddle/trt_fp32/trt_fp16/trt_int8)
        use_dynamic_shape (bool): use dynamic shape or not
        trt_min_shape (int): min shape for dynamic shape in trt
        trt_max_shape (int): max shape for dynamic shape in trt
        trt_opt_shape (int): opt shape for dynamic shape in trt
        trt_calib_mode (bool): If the model is produced by TRT offline quantitative
            calibration, trt_calib_mode need to set True
        delete_shuffle_pass (bool): whether to remove shuffle_channel_detect_pass in TensorRT.
                                    Used by action model.
    Returns:
        predictor (PaddlePredictor): AnalysisPredictor
    Raises:
        ValueError: predict by TensorRT need device == 'GPU'.
    """
    if device != 'GPU' and run_mode != 'paddle':
        raise ValueError(
            "Predict by TensorRT mode: {}, expect device=='GPU', but device == {}"
            .format(run_mode, device))
    infer_model = os.path.join(model_dir, 'model.pdmodel')
    infer_params = os.path.join(model_dir, 'model.pdiparams')
    if not os.path.exists(infer_model):
        infer_model = os.path.join(model_dir, 'inference.pdmodel')
        infer_params = os.path.join(model_dir, 'inference.pdiparams')
        if not os.path.exists(infer_model):
            raise ValueError(
                "Cannot find any inference model in dir: {},".format(model_dir))
    config = Config(infer_model, infer_params)
    if device == 'GPU':
        # initial GPU memory(M), device ID
        config.enable_use_gpu(200, 0)
        # optimize graph and fuse op
        config.switch_ir_optim(True)
    elif device == 'XPU':
        if config.lite_engine_enabled():
            config.enable_lite_engine()
        config.enable_xpu(10 * 1024 * 1024)
    elif device == 'NPU':
        if config.lite_engine_enabled():
            config.enable_lite_engine()
        config.enable_npu()
    else:
        config.disable_gpu()
        config.set_cpu_math_library_num_threads(cpu_threads)
        if enable_mkldnn:
            try:
                # cache 10 different shapes for mkldnn to avoid memory leak
                config.set_mkldnn_cache_capacity(10)
                config.enable_mkldnn()
                if enable_mkldnn_bfloat16:
                    config.enable_mkldnn_bfloat16()
            except Exception as e:
                print(
                    "The current environment does not support `mkldnn`, so disable mkldnn."
                )
                pass

    precision_map = {
        'trt_int8': Config.Precision.Int8,
        'trt_fp32': Config.Precision.Float32,
        'trt_fp16': Config.Precision.Half
    }
    if run_mode in precision_map.keys():
        config.enable_tensorrt_engine(
            workspace_size=(1 << 25) * batch_size,
            max_batch_size=batch_size,
            min_subgraph_size=min_subgraph_size,
            precision_mode=precision_map[run_mode],
            use_static=False,
            use_calib_mode=trt_calib_mode)

        if use_dynamic_shape:
            min_input_shape = {
                'image': [batch_size, 3, trt_min_shape, trt_min_shape],
                'scale_factor': [batch_size, 2]
            }
            max_input_shape = {
                'image': [batch_size, 3, trt_max_shape, trt_max_shape],
                'scale_factor': [batch_size, 2]
            }
            opt_input_shape = {
                'image': [batch_size, 3, trt_opt_shape, trt_opt_shape],
                'scale_factor': [batch_size, 2]
            }
            config.set_trt_dynamic_shape_info(min_input_shape, max_input_shape,
                                              opt_input_shape)
            print('trt set dynamic shape done!')

    # disable print log when predict
    config.disable_glog_info()
    # enable shared memory
    config.enable_memory_optim()
    # disable feed, fetch OP, needed by zero_copy_run
    config.switch_use_feed_fetch_ops(False)
    if delete_shuffle_pass:
        config.delete_pass("shuffle_channel_detect_pass")
    predictor = create_predictor(config)
    return predictor, config


def pdf2html(input_path):
    doc = fitz.open(input_path)

    html_content = []
    for page in range(len(doc)):
        html_content.append(doc[page].get_text('html'))
    return html_content


def decodestylestr(style_attrs, attr):
    attrvalue = ""
    styles = style_attrs.split(";")
    for sty in styles:
        k, v = sty.split(":")
        v = v.replace("pt", "")
        if k == attr:
            attrvalue = v
    return attrvalue


def pdf2list(input_path):
    html_content = pdf2html(input_path)
    allcontents = []
    for ip in range(len(html_content)):
        contents = []
        bs_obj = BeautifulSoup(html_content[ip], "html.parser")

        # 读取P节点
        ptag = bs_obj.findAll("p")
        # 取P节点下文本以及其对应的left值和font-family和font-size的值。
        for p in ptag:
            ptext = p.text
            ptextnospace = ptext.replace(" ", "")
            # 如果当前节点text为空，则下一个
            if len(ptextnospace) == 0:  # 当前文本为空字符串
                continue
            else:
                pass

            '''
            读取P节点下的style属性
            '''
            postioninfo = ('', '',)
            if 'style' in p.attrs:
                attributes = p.attrs['style']
                leftvalue = decodestylestr(attributes, "left")
                topvalue = decodestylestr(attributes, "top")
                postioninfo = (leftvalue, topvalue)
            else:
                postioninfo = ('', '',)

                pass

            '''
            获取P节点下的span节点，并读取取style属性，主要包括字体名称、字体大小、字体颜色，是否加粗pdf2html没有提取到。如果有也应该获取
            pspans = p.find_all("span",recursive=False ) recursive=False只获取当前节点下的子节点，不循环其孙子及以下节点
            '''
            pspans = p.find_all("span")
            pspansstyles = []

            for pspan in pspans:
                pspantext = pspan.text
                pspantext = pspantext.replace(" ", "")
                if len(pspantext) > 0:  # 当前span节点不为空。
                    if 'style' in pspan.attrs:
                        attributes = pspan.attrs['style']
                        fontfamilyvalue = decodestylestr(attributes, "font-family")
                        fontsizevalue = decodestylestr(attributes, "font-size")
                        fontcolorvalue = decodestylestr(attributes, "color")
                        pspansstyle = (fontfamilyvalue, fontsizevalue, fontcolorvalue)
                        if pspansstyle in pspansstyles:
                            pspansstyles.remove(pspansstyle)
                        pspansstyles.append(pspansstyle)
                    else:
                        pass
            ptextattrs = [ptext, postioninfo, pspansstyles, ip]
            contents.append(ptextattrs)
        allcontents.append(contents)
    return allcontents


def findstartpage(pdfpath, ratiothr=0.1):
    ###根据mode和content 做进一步的判断
    contents = pdf2list(pdfpath)
    startpage = []
    sizetmp = []
    for ip in range(len(contents)):
        pagecontents = contents[ip]

        for ic in range(len(pagecontents)):
            content = pagecontents[ic]
            for keyword in keywords:
                if "".join(keyword.split()) in "".join(content[0].upper().split()):
                    if content[-1] not in startpage:
                        startpage.append(content[-1])
                        sizetmp.append(float(content[2][0][1]))
                else:
                    if "".join(content[0].upper().split()) in "".join(keyword.split()):
                        if abs(len("".join(content[0].upper().split())) - len("".join(keyword.split()))) < 3:
                            if content[-1] not in startpage:
                                startpage.append(content[-1])
                                sizetmp.append(float(content[2][0][1]))
                                # print(content)
    resultpages = []
    if startpage != []:
        for index in np.argsort(sizetmp)[::-1]:
            if startpage[index] not in resultpages:
                resultpages.append(startpage[index])

    if 0 in resultpages:
        idx = resultpages.index(0)
        resultpages.insert(0, resultpages.pop(idx))
    return resultpages


def generateDCT(pdfPath, netG=[], zoom_x=2, zoom_y=2, rotation_angle=0, intervallength=4, ratiothr=0.1):
    try:
        startpagelist = findstartpage(pdfPath, ratiothr=ratiothr)
        allimglist = []
        shapelist = []
        if startpagelist != []:
            for startpage in startpagelist:
                pdf = fitz.open(pdfPath)
                page = pdf[startpage]
                # 设置缩放和旋转系数
                trans = fitz.Matrix(zoom_x, zoom_y).preRotate(rotation_angle)
                pix = page.getPixmap(matrix=trans, alpha=False)
                w, h = pix.width, pix.height
                # 开始写图像
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                allimg = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
                for pg in range(startpage + 1, min(pdf.pageCount, startpage + intervallength)):
                    # print(pg)
                    page = pdf[pg]
                    # 设置缩放和旋转系数
                    trans = fitz.Matrix(zoom_x, zoom_y).preRotate(rotation_angle)
                    pix = page.getPixmap(matrix=trans, alpha=False)
                    # 开始写图像
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
                    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
                    if netG != []:
                        img = pdfdw(img, netG)
                    allimg = np.concatenate((allimg, img), axis=0)
                allimglist.append(allimg)
                shapelist.append((w, h))
            return allimglist, startpagelist, shapelist
        else:
            return [], [], []
    except:
        return [], [], []


def pdfdw(imgs, netG):
    _, _, h, w = imgs.shape
    if h < 16000 and w < 16000:  # 1600
        with paddle.no_grad():
            tt = netG(imgs)
            res = tt
            res += paddle.flip(netG(paddle.flip(imgs, axis=[2])), axis=[2])
            res += paddle.flip(netG(paddle.flip(imgs, axis=[3])), axis=[3])
            res += paddle.flip(netG(paddle.flip(imgs, axis=[2, 3])), axis=[2, 3])
            res = res / 4  # 16 + 480
    else:
        step = min(h, w, 800)
        res = paddle.zeros_like(imgs, dtype='float32')
        for i in range(0, h, step):
            for j in range(0, w, step):
                with paddle.no_grad():
                    clip = imgs[:, :, i:(i + step), j:(j + step)]
                    clip = paddle.to_tensor(clip)
                    tt = netG(clip)
                    g_images_clip = tt
                    g_images_clip += paddle.flip(netG(paddle.flip(clip, axis=[2])), axis=[2])
                    g_images_clip += paddle.flip(netG(paddle.flip(clip, axis=[3])), axis=[3])
                    g_images_clip += paddle.flip(netG(paddle.flip(clip, axis=[2, 3])), axis=[2, 3])
                    g_images_clip = g_images_clip / 4  # 16 + 480
                    res[:, :, i:(i + step), j:(j + step)] = g_images_clip
    res = pd_tensor2img(res)
    return res


def ImageTransform():
    return Compose([
        ToTensor(),
    ])


detector = eval(detector_func)(
    model_dir,
    device=device,
    run_mode=run_mode,
    batch_size=batch_size,
    trt_min_shape=trt_min_shape,
    trt_max_shape=trt_max_shape,
    trt_opt_shape=trt_opt_shape,
    trt_calib_mode=trt_calib_mode,
    cpu_threads=cpu_threads,
    enable_mkldnn=enable_mkldnn,
    enable_mkldnn_bfloat16=enable_mkldnn_bfloat16,
    threshold=threshold,
    output_dir=output_dir)

detector1 = eval(detector_func)(
    model_dir1,
    device=device,
    run_mode=run_mode,
    batch_size=batch_size,
    trt_min_shape=trt_min_shape,
    trt_max_shape=trt_max_shape,
    trt_opt_shape=trt_opt_shape,
    trt_calib_mode=trt_calib_mode,
    cpu_threads=cpu_threads,
    enable_mkldnn=enable_mkldnn,
    enable_mkldnn_bfloat16=enable_mkldnn_bfloat16,
    threshold=threshold,
    output_dir=output_dir1)


@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    pdf_path = data.get('pdf_path')
    name = data.get('name')
    imglist, startpagelist, shapelist = generateDCT(pdf_path)
    detectflag = 1
    image_paths = []
    base_path = os.path.dirname(pdf_path)
    if imglist != []:
        for index in range(len(imglist)):
            img, startpage, (pagew, pageh) = imglist[index], startpagelist[index], shapelist[index]
            if detectflag:
                imgh, imgw = img.shape[:2]
                results = detector.predict_image([img])[0]
                flag = 0
                for j in range(len(results)):
                    if int(results[j][0]) == 0:
                        flag = 1
                if flag:
                    for j in range(len(results)):
                        label, score, xmin, ymin, xmax, ymax = results[j]
                        xmin, ymin, xmax, ymax = int(max(0, xmin - 200)), int(max(0, ymin - 200)), int(
                            min(xmax + 200, imgw)), int(min(ymax + 200, imgh))
                        regionimg = img[ymin:ymax, xmin:xmax, :]
                        regionresults = detector1.predict_image([regionimg])[0]
                        if len(regionresults) > 0:
                            finebox = regionresults[np.argmax(regionresults[:, 1])]
                            finebox[2] += xmin
                            finebox[3] += ymin
                            finebox[4] += xmin
                            finebox[5] += ymin
                            results[j] = finebox
                    results = sdnms(results)
                    # results = results
                else:
                    results = []
                imgid = 0
                # print(results, 1111)
                for j in range(len(results)):
                    label, score, xmin, ymin, xmax, ymax = results[j]
                    if label == 0:
                        # xmin,ymin,xmax,ymax = max(0,xmin-5),max(0,ymin-5),min(xmax+5,imgw),min(ymax+5,imgh)
                        box_w, box_h = xmax - xmin, ymax - ymin
                        clipimg = img[int(ymin):int(ymax), int(xmin):int(xmax), :]
                        # print(clipimg.shape)
                        # cv2.imwrite('./infer_output/unHD_%s_%s.png'%(name,j), clipimg)
                        currentpage = int(np.floor(ymin / pageh)) + startpage
                        currentxmin, currentxmax, currentyin, currentymax = xmin / pagew, xmax / pagew, (
                                ymin - np.floor(ymin / pageh) * pageh) / pageh, (ymax - np.floor(
                            ymin / pageh) * pageh) / pageh
                        # print(currentpage,ymin,ymax,pageh,np.floor(ymin/pageh)*pageh,np.floor(ymax/pageh)*pageh)
                        pdf = fitz.open(pdf_path)
                        page = pdf[currentpage]
                        # 设置缩放和旋转系数
                        HDSIZE = 1000
                        zoom_x, zoom_y, rotation_angle = 2, 2, 0
                        HDscale = max(HDSIZE / box_w, HDSIZE / box_h)
                        zoom_x, zoom_y = zoom_x * HDscale, zoom_y * HDscale
                        trans = fitz.Matrix(zoom_x, zoom_y).preRotate(rotation_angle)
                        pix = page.getPixmap(matrix=trans, alpha=False)
                        w, h = pix.width, pix.height
                        # 开始写图像
                        HDimg = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        HDimg = cv2.cvtColor(np.asarray(HDimg), cv2.COLOR_RGB2BGR)
                        HDimgh, HDimgw = HDimg.shape[:2]
                        HDclipimgxmin, HDclipimgxmax, HDclipimgymin, HDclipimgymax = int(currentxmin * w), int(
                            currentxmax * w), int(currentyin * h), int(currentymax * h)
                        HDclipimgxmin, HDclipimgymin, HDclipimgxmax, HDclipimgymax = max(0, HDclipimgxmin - 3), max(0,
                                                                                                                    HDclipimgymin - 3), min(
                            HDclipimgxmax + 3, HDimgw), min(HDclipimgymax + 3, HDimgh)
                        HDclipimg = HDimg[HDclipimgymin:HDclipimgymax, HDclipimgxmin:HDclipimgxmax, :]
                        img_path = '%s/%s_%s.jpg' % (base_path, name, imgid)
                        cv2.imwrite(img_path, HDclipimg)
                        image_paths.append(img_path)
                        imgid += 1
                        detectflag = 0
    print('%s 处理完毕' % name)
    return jsonify({"image_paths": image_paths})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
