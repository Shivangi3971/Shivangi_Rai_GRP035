import argparse
import os, sys
import os.path as osp
import torchvision
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import transforms
import network, loss
from torch.utils.data import DataLoader
from data_list import ImageList, ImageList_idx
import random, pdb, math, copy
from tqdm import tqdm
from scipy.spatial.distance import cdist
from sklearn.metrics import confusion_matrix
import distutils
import distutils.util
import logging

import sys
sys.path.append("/data3/Shivangi/KUDA/util/")
from utils import resetRNGseed, init_logger, get_hostname, get_pid

import time
timestamp = time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime())

torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

def op_copy(optimizer):
    for param_group in optimizer.param_groups:
        param_group['lr0'] = param_group['lr']
    return optimizer

def lr_scheduler(optimizer, iter_num, max_iter, gamma=10, power=0.75):
    decay = (11 + gamma * iter_num / max_iter) ** (-power)
    # decay = (1 + gamma) ** (-power)
    for param_group in optimizer.param_groups:
        param_group['lr'] = param_group['lr0'] * decay
        param_group['weight_decay'] = 1e-3
        param_group['momentum'] = 0.9
        param_group['nesterov'] = True
    return optimizer

def image_train(resize_size=256, crop_size=224, alexnet=False):
  if not alexnet:
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                   std=[0.229, 0.224, 0.225])
  else:
    normalize = Normalize(meanfile='./ilsvrc_2012_mean.npy')
  return  transforms.Compose([
        transforms.Resize((resize_size, resize_size)),
        transforms.RandomCrop(crop_size),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        normalize
    ])

def image_test(resize_size=256, crop_size=224, alexnet=False):
  if not alexnet:
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                   std=[0.229, 0.224, 0.225])
  else:
    normalize = Normalize(meanfile='./ilsvrc_2012_mean.npy')
  return  transforms.Compose([
        transforms.Resize((resize_size, resize_size)),
        transforms.CenterCrop(crop_size),
        transforms.ToTensor(),
        normalize
    ])

def data_load(args): 
    ## prepare data
    dsets = {}
    dset_loaders = {}
    train_bs = args.batch_size
    txt_tar = open(args.t_dset_path).readlines()
    txt_test = open(args.test_dset_path).readlines()

    if not args.da == 'uda':
        label_map_s = {}
        for i in range(len(args.src_classes)):
            label_map_s[args.src_classes[i]] = i

        new_tar = []
        for i in range(len(txt_tar)):
            rec = txt_tar[i]
            reci = rec.strip().split(' ')
            if int(reci[1]) in args.tar_classes:
                if int(reci[1]) in args.src_classes:
                    line = reci[0] + ' ' + str(label_map_s[int(reci[1])]) + '\n'
                    new_tar.append(line)
                else:
                    line = reci[0] + ' ' + str(len(label_map_s)) + '\n'
                    new_tar.append(line)
        txt_tar = new_tar.copy()
        txt_test = txt_tar.copy()

    dsets["target"] = ImageList_idx(txt_tar, root="/data3/Shivangi/KUDA/data/{}/".format(args.dset), transform=image_train())
    dset_loaders["target"] = DataLoader(dsets["target"], batch_size=train_bs, shuffle=True, num_workers=args.worker, drop_last=False)
    dsets["test"] = ImageList_idx(txt_test, root="/data3/Shivangi/KUDA/data/{}/".format(args.dset), transform=image_test())
    dset_loaders["test"] = DataLoader(dsets["test"], batch_size=train_bs*3, shuffle=False, num_workers=args.worker, drop_last=False)
    dsets["target_te"] = ImageList(txt_tar, root="/data3/Shivangi/KUDA/data/{}/".format(args.dset), transform=image_test())
    dset_loaders["target_te"] = DataLoader(dsets["target_te"], batch_size=train_bs, shuffle=True, num_workers=args.worker, drop_last=False)

    return dset_loaders

def cal_acc(loader, netF, netB, netC, flag=False):
    start_test = True
    with torch.no_grad():
        iter_test = iter(loader)
        for i in range(len(loader)):
            data = next(iter_test)#iter_test.next()
            inputs = data[0]
            labels = data[1]
            inputs = inputs.cuda()
            outputs = netC(netB(netF(inputs)))
            if start_test:
                all_output = outputs.float().cpu()
                all_label = labels.float()
                start_test = False
            else:
                all_output = torch.cat((all_output, outputs.float().cpu()), 0)
                all_label = torch.cat((all_label, labels.float()), 0)
    all_output = nn.Softmax(dim=1)(all_output)
    _, predict = torch.max(all_output, 1)
    accuracy = torch.sum(torch.squeeze(predict).float() == all_label).item() / float(all_label.size()[0])
    mean_ent = torch.mean(loss.Entropy(all_output)).cpu().data.item() / np.log(all_label.size()[0])

    if flag:
        matrix = confusion_matrix(all_label, torch.squeeze(predict).float())
        matrix = matrix[np.unique(all_label).astype(int),:]
        acc = matrix.diagonal()/matrix.sum(axis=1) * 100
        aacc = acc.mean()
        aa = [str(np.round(i, 2)) for i in acc]
        acc = ' '.join(aa)
        return aacc, acc, predict, mean_ent
    else:
        return accuracy*100, mean_ent, predict, mean_ent

def train_target(args):
    dset_loaders = data_load(args)
    if args.net[0:3] == 'res': 
        netF = network.ResBase(res_name=args.net).cuda()
        
    netB = network.feat_bootleneck(type=args.classifier, feature_dim=netF.in_features, bottleneck_dim=args.bottleneck).cuda()
    netC = network.feat_classifier(type=args.layer, class_num=args.class_num, bottleneck_dim=args.bottleneck).cuda()
   
    modelpath = osp.join(args.output_dir, "{}_{}_{}_{}_target_F".format(args.timestamp, args.s, args.t, args.net) + ".pt" )
    netF.load_state_dict(torch.load(modelpath))
    modelpath = osp.join(args.output_dir, "{}_{}_{}_{}_target_B".format(args.timestamp, args.s, args.t, args.net) + ".pt")
    netB.load_state_dict(torch.load(modelpath))
    modelpath = osp.join(args.output_dir, "{}_{}_{}_{}_target_C".format(args.timestamp, args.s, args.t, args.net) + ".pt")
    netC.load_state_dict(torch.load(modelpath))

    param_group = []
    for k, v in netF.named_parameters():
        param_group += [{'params': v, 'lr': args.lr*0.1}]
    for k, v in netB.named_parameters():
        param_group += [{'params': v, 'lr': args.lr}]
    for k, v in netC.named_parameters():
        param_group += [{'params': v, 'lr': args.lr}]

    optimizer = optim.SGD(param_group)
    optimizer = op_copy(optimizer)

    max_iter = args.max_epoch * len(dset_loaders["target"])
    interval_iter = max_iter // 10
    iter_num = 0

    netF.eval()
    netB.eval()
    netC.eval()
    acc_s_te, _, pry, mean_ent = cal_acc(dset_loaders['test'], netF, netB, netC, False)
    log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy={:.2f}%, Ent={:.3f}'.format(args.s, args.t, iter_num, max_iter, acc_s_te, mean_ent)
    if args.dset == 'visda-2017':
        acc_s_te, acc_list, pry, mean_ent = cal_acc(dset_loaders['test'], netF, netB, netC, True)
        log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy = {:.2f}%, Ent = {:.4f}'.format(args.s, args.t, iter_num, max_iter, acc_s_te,
                                                                                      mean_ent) + '\n' + acc_list

    logging.info(log_str)
    netF.train()
    netB.train()
    netC.train()

    old_pry = 0
    while iter_num < max_iter:
        optimizer.zero_grad()
        try:
            inputs_test, _, tar_idx = next(iter_test)#iter_test.next()
        except:
            iter_test = iter(dset_loaders["target"])
            inputs_test, _, tar_idx = next(iter_test)#iter_test.next()

        if inputs_test.size(0) == 1:
            continue

        inputs_test = inputs_test.cuda()

        iter_num += 1
        lr_scheduler(optimizer, iter_num=iter_num, max_iter=max_iter, power=0.75)

        features_test = netB(netF(inputs_test))
        outputs_test = netC(features_test)

        softmax_out = nn.Softmax(dim=1)(outputs_test)
        entropy_loss = torch.mean(loss.Entropy(softmax_out))

        msoftmax = softmax_out.mean(dim=0)
        gentropy_loss = -torch.sum(msoftmax * torch.log(msoftmax + 1e-5))
        entropy_loss -= gentropy_loss
        entropy_loss.backward()
        optimizer.step()

        if iter_num % interval_iter == 0 or iter_num == max_iter:
            netF.eval()
            netB.eval()
            netC.eval()
            acc_s_te, _, pry, mean_ent = cal_acc(dset_loaders['test'], netF, netB, netC, False)
            log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy={:.2f}%, Ent={:.3f}'.format(args.s, args.t, iter_num, max_iter, acc_s_te, mean_ent)
            if args.dset == 'visda-2017':
                acc_s_te, acc_list, pry, mean_ent = cal_acc(dset_loaders['test'], netF, netB, netC, True)
                log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy = {:.2f}%, Ent = {:.4f}'.format(args.s, args.t, iter_num, max_iter, acc_s_te, mean_ent) + '\n' + acc_list
            logging.info(log_str)

            netF.train()
            netB.train()
            netC.train()

            if torch.abs(pry - old_pry).sum() == 0:
                break
            else:
                old_pry = pry.clone()
 
    return netF, netB, netC

def print_args(args):
    s = "==========================================\n"
    for arg, content in args.__dict__.items():
        s += "{}:{}\n".format(arg, content)
    return s

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='DINE')
    parser.add_argument('--gpu_id', type=str, nargs='?', default='0', help="device id to run")
    parser.add_argument('--s', type=str, default=None, help="source")
    parser.add_argument('--t', type=str, default=None, help="target")
    parser.add_argument('--max_epoch', type=int, default=30, help="max iterations")
    parser.add_argument('--batch_size', type=int, default=64, help="batch_size")
    parser.add_argument('--worker', type=int, default=4, help="number of workers")
    parser.add_argument('--dset', type=str, default='office-home', choices=['visda-2017', 'office31', 'image-clef', 'office-home', 'office-caltech'])
    parser.add_argument('--lr', type=float, default=1e-2, help="learning rate")
    parser.add_argument('--net', type=str, default='resnet50', help="alexnet, vgg16, resnet18, resnet50, resnext50")
    parser.add_argument('--net_src', type=str, default='resnet50', help="alexnet, vgg16, resnet18, resnet34, resnet50, resnet101")
    parser.add_argument('--seed', type=int, default=2020, help="random seed")

    parser.add_argument('--bottleneck', type=int, default=256)
    parser.add_argument('--layer', type=str, default="wn", choices=["linear", "wn"])
    parser.add_argument('--classifier', type=str, default="bn", choices=["ori", "bn"])
    parser.add_argument('--output', type=str, default='san')
    parser.add_argument('--da', type=str, default='uda', choices=['uda', 'pda'])

    parser.add_argument('--timestamp', default=timestamp, type=str, help='timestamp')
    parser.add_argument('--use_file_logger', default='True', type=lambda x: bool(distutils.util.strtobool(x)),
                        help='whether use file logger')
    parser.add_argument('--names', default=[], type=list, help='names of tasks')
    parser.add_argument('--method', type=str, default=None)

    args = parser.parse_args()
    if args.dset == 'office-home':
        args.names = ['Art', 'Clipart', 'Product', 'Real_World']
        args.class_num = 65
    if args.dset == 'visda-2017':
        args.names = ['train', 'validation']
        args.class_num = 12
    if args.dset == 'office31':
        args.names = ['amazon', 'dslr', 'webcam']
        args.class_num = 31

    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id
    resetRNGseed(args.seed)

    if args.dset == 'office-home':
        if args.da == 'pda':
            args.class_num = 65
            args.src_classes = [i for i in range(65)]
            args.tar_classes = [33, 32, 36, 15, 19, 2, 46, 49, 48, 53, 47, 54, 4, 18, 57, 23, 0, 45, 1, 38, 5, 13, 50, 11, 58]

    if args.method is not None:
        dir = "{}_{}_{}_{}".format(args.timestamp, args.s, args.da, args.method)
        if args.use_file_logger:
            init_logger(dir, True, '../logs/DINE/{}/'.format(args.method))
    else:
        dir = "{}_{}_{}".format(args.timestamp, args.s, args.da)
        if args.use_file_logger:
            init_logger(dir, True, '../logs/DINE/')
    logging.info("{}:{}".format(get_hostname(), get_pid()))

    folder = '/data3/Shivangi/KUDA/data/'
    for t in args.names:
        if t == args.s:
            continue
        args.t = t
        args.s_dset_path = folder + args.dset + '/image_list/' + args.s + '.txt'
        args.t_dset_path = folder + args.dset + '/image_list/' + args.t + '.txt'
        args.test_dset_path = folder + args.dset + '/image_list/' + args.t + '.txt'

        args.output_dir = "../checkpoints/DINE/{}/target/{}/".format(args.seed, args.da)


        if not osp.exists(args.output_dir):
            os.system('mkdir -p ' + args.output_dir)
        if not osp.exists(args.output_dir):
            os.mkdir(args.output_dir)

        logging.info(print_args(args))

        train_target(args)
