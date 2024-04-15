import argparse
import os.path as osp
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import transforms
import network, loss
from torch.utils.data import DataLoader
from data_list import ImageList_idx
from scipy.spatial.distance import cdist
from sklearn.metrics import confusion_matrix
import distutils
import distutils.util
import logging

import sys, os
sys.path.append("../util/")
from utils import resetRNGseed, init_logger, get_hostname, get_pid

sys.path.append("../pklib")
from pksolver import PK_solver

import time
timestamp = time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime())

torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False


def op_copy(optimizer):
    for param_group in optimizer.param_groups:
        param_group['lr0'] = param_group['lr']
    return optimizer

def lr_scheduler(optimizer, iter_num, max_iter, gamma=10, power=0.75):
    decay = (1 + gamma * iter_num / max_iter) ** (-power)
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

    dsets["target"] = ImageList_idx(txt_tar, root="../data/{}/".format(args.dset), transform=image_train())
    dset_loaders["target"] = DataLoader(dsets["target"], batch_size=train_bs, shuffle=True, num_workers=args.worker, drop_last=False)

    dsets["test"] = ImageList_idx(txt_test, root="../data/{}/".format(args.dset), transform=image_test())
    dset_loaders["test"] = DataLoader(dsets["test"], batch_size=train_bs*3, shuffle=False, num_workers=args.worker, drop_last=False)
    dsets["valid"] = ImageList_idx(txt_tar, root="../data/{}/".format(args.dset), transform=image_train() if args.use_train_transform else image_test())
    dset_loaders["valid"] = DataLoader(dsets["valid"], batch_size=train_bs * 3, shuffle=False, num_workers=args.worker, drop_last=False)

    return dset_loaders

def cal_acc(loader, netF, netB, netC):
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
    _, predict = torch.max(all_output, 1)
    acc = torch.sum(torch.squeeze(predict).float() == all_label).item() / float(all_label.size()[0]) * 100
    mean_ent = torch.mean(loss.Entropy(nn.Softmax(dim=1)(all_output))).cpu().data.item()

    matrix = confusion_matrix(all_label, torch.squeeze(predict).float())
    acc_list = matrix.diagonal() / matrix.sum(axis=1) * 100
    per_class_acc = acc_list.mean()
    if args.da == 'pda':
        acc_list = ''
        per_class_acc = 0
    acc_list = ' '.join([str(np.round(i, 2)) for i in acc_list])
    return acc, mean_ent, per_class_acc, acc_list


def train_target(args):
    dset_loaders = data_load(args)
    ## set base network
    if args.net[0:3] == 'res':
        netF = network.ResBase(res_name=args.net).cuda()
    elif args.net[0:3] == 'vgg':
        netF = network.VGGBase(vgg_name=args.net).cuda()  

    netB = network.feat_bootleneck(type=args.classifier, feature_dim=netF.in_features, bottleneck_dim=args.bottleneck).cuda()
    netC = network.feat_classifier(type=args.layer, class_num = args.class_num, bottleneck_dim=args.bottleneck).cuda()

    modelpath = osp.join(args.output_dir_src, "{}_{}_source_F.pt".format(args.s, args.net))
    netF.load_state_dict(torch.load(modelpath))
    modelpath = osp.join(args.output_dir_src, "{}_{}_source_B.pt".format(args.s, args.net))
    netB.load_state_dict(torch.load(modelpath))
    modelpath = osp.join(args.output_dir_src, "{}_{}_source_C.pt".format(args.s, args.net))
    netC.load_state_dict(torch.load(modelpath))
    netC.eval()
    for k, v in netC.named_parameters():
        v.requires_grad = False

    param_group = []
    for k, v in netF.named_parameters():
        if args.lr_decay1 > 0:
            param_group += [{'params': v, 'lr': args.lr * args.lr_decay1}]
        else:
            v.requires_grad = False
    for k, v in netB.named_parameters():
        if args.lr_decay2 > 0:
            param_group += [{'params': v, 'lr': args.lr * args.lr_decay2}]
        else:
            v.requires_grad = False

    optimizer = optim.SGD(param_group)
    optimizer = op_copy(optimizer)

    max_iter = args.max_epoch * len(dset_loaders["target"])
    interval_iter = max_iter // args.interval
    iter_num = 0

    # get ground-truth label probabilities of target domain
    start = True
    iter_valid = iter(dset_loaders['valid'])
    for _ in range(len(dset_loaders['valid'])):
        data = next(iter_valid)#iter_valid.next()
        labels = data[1]
        if start:
            all_label = labels.long()
            start = False
        else:
            all_label = torch.cat((all_label, labels.long()), 0)

    cls_probs = torch.eye(args.class_num)[all_label].sum(0)
    cls_probs = cls_probs / cls_probs.sum()

    if args.pk_dratio < 1.0:
        ND = int(len(all_label)*args.pk_dratio)
        cls_probs_sample = torch.eye(args.class_num)[all_label[torch.randint(len(all_label), (ND,))]].sum(0)
        cls_probs_sample = cls_probs_sample / cls_probs_sample.sum()
        err = (cls_probs_sample-cls_probs)/cls_probs
        logging.info('True probs: {}'.format(cls_probs))
        logging.info('Sample probs: {}'.format(cls_probs_sample))
        logging.info('Probs err: {}, max err: {}, mean err{}'.format(err, err.abs().max(), err.abs().mean()))
        cls_probs = cls_probs_sample

    pk_solver = PK_solver(all_label.shape[0], args.class_num, pk_prior_weight=args.pk_prior_weight)
    if args.pk_type == 'ub':
        pk_solver.create_C_ub(cls_probs.cpu().numpy(), args.pk_uconf)
    elif args.pk_type == 'br':
        pk_solver.create_C_br(cls_probs.cpu().numpy(), args.pk_uconf)
    elif args.pk_type == 'ub+rel':
        pk_solver.create_C_ub(cls_probs.cpu().numpy(), args.pk_uconf)
        pk_solver.create_C_br(cls_probs.cpu().numpy(), 1.0)
    elif args.pk_type == 'ub_partial':
        pk_solver.create_C_ub_partial(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'ub_partial_reverse':
        pk_solver.create_C_ub_partial_reverse(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'ub_partial_rand':
        pk_solver.create_C_ub_partial_rand(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'br_partial':
        pk_solver.create_C_br_partial(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'br_partial_reverse':
        pk_solver.create_C_br_partial_reverse(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'br_partial_rand':
        pk_solver.create_C_br_partial_rand(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_NC)
    elif args.pk_type == 'ub_noisy':
        pk_solver.create_C_ub_noisy(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_noise)
    elif args.pk_type == 'br_noisy':
        pk_solver.create_C_br_noisy(cls_probs.cpu().numpy(), args.pk_uconf, args.pk_noise)

    epoch = 0
    while iter_num < max_iter:
        try:
            inputs_test, _, tar_idx = next(iter_test)#iter_test.next()
        except:
            iter_test = iter(dset_loaders["target"])
            inputs_test, _, tar_idx = next(iter_test)#iter_test.next()

        if inputs_test.size(0) == 1:
            continue

        if iter_num % interval_iter == 0 and args.cls_par > 0:
            netF.eval()
            netB.eval()
            mem_label = obtain_label(dset_loaders['valid'], netF, netB, netC, args, pk_solver, epoch)
            mem_label = torch.from_numpy(mem_label).cuda()
            netF.train()
            netB.train()
            epoch += 1


        inputs_test = inputs_test.cuda()

        iter_num += 1
        lr_scheduler(optimizer, iter_num=iter_num, max_iter=max_iter)

        features_test = netB(netF(inputs_test))
        outputs_test = netC(features_test)

        if args.cls_par > 0:
            pred = mem_label[tar_idx]
            classifier_loss = nn.CrossEntropyLoss()(outputs_test, pred)
            classifier_loss *= args.cls_par
            if iter_num < interval_iter and args.dset == "visda-2017":
                classifier_loss *= 0
        else:
            classifier_loss = torch.tensor(0.0).cuda()

        if args.ent:
            softmax_out = nn.Softmax(dim=1)(outputs_test)
            entropy_loss = torch.mean(loss.Entropy(softmax_out))
            if args.gent:
                msoftmax = softmax_out.mean(dim=0)
                gentropy_loss = torch.sum(-msoftmax * torch.log(msoftmax + args.epsilon))
                entropy_loss -= gentropy_loss
            im_loss = entropy_loss * args.ent_par
            classifier_loss += im_loss

        optimizer.zero_grad()
        classifier_loss.backward()
        optimizer.step()

        if iter_num % interval_iter == 0 or iter_num == max_iter:
            netF.eval()
            netB.eval()

            if args.dset=='visda-2017':
                acc, _, per_class_acc, acc_list = cal_acc(dset_loaders['test'], netF, netB, netC)
                log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy = {:.2f}%    Per_class_accuracy={:.2f}'.format(args.s, args.t, iter_num, max_iter, acc, per_class_acc) + '\n' + acc_list
            else:
                acc, _, per_class_acc, acc_list = cal_acc(dset_loaders['test'], netF, netB, netC)
                log_str = 'Task: {}->{}, Iter:{}/{}; Accuracy = {:.2f}%    Per_class_accuracy={:.2f}'.format(args.s, args.t, iter_num, max_iter, acc, per_class_acc)

            logging.info(log_str)
            netF.train()
            netB.train() 

    if args.issave:   
        torch.save(netF.state_dict(), osp.join(args.output_dir, "{}_{}_{}_{}_target_F_".format(args.timestamp, args.s, args.t, args.net) + args.savename + ".pt"))
        torch.save(netB.state_dict(), osp.join(args.output_dir, "{}_{}_{}_{}_target_B_".format(args.timestamp, args.s, args.t, args.net) + args.savename + ".pt"))
        torch.save(netC.state_dict(), osp.join(args.output_dir, "{}_{}_{}_{}_target_C_".format(args.timestamp, args.s, args.t, args.net) + args.savename + ".pt"))
        
    return netF, netB, netC

def print_args(args):
    s = "==========================================\n"
    for arg, content in args.__dict__.items():
        s += "{}:{}\n".format(arg, content)
    return s

def obtain_label(loader, netF, netB, netC, args, pk_solver, epoch):
    start_test = True
    with torch.no_grad():
        iter_test = iter(loader)
        for _ in range(len(loader)):
            data = next(iter_test)#iter_test.next()
            inputs = data[0]
            labels = data[1]
            inputs = inputs.cuda()
            feas = netB(netF(inputs))
            outputs = netC(feas)
            if start_test:
                all_fea = feas.float().cpu()
                all_output = outputs.float().cpu()
                all_label = labels.float()
                start_test = False
            else:
                all_fea = torch.cat((all_fea, feas.float().cpu()), 0)
                all_output = torch.cat((all_output, outputs.float().cpu()), 0)
                all_label = torch.cat((all_label, labels.float()), 0)

    all_output = nn.Softmax(dim=1)(all_output)
    ent = torch.sum(-all_output * torch.log(all_output + args.epsilon), dim=1)
    unknown_weight = 1 - ent / np.log(args.class_num)
    _, predict = torch.max(all_output, 1)

    accuracy = torch.sum(torch.squeeze(predict).float() == all_label).item() / float(all_label.size()[0])
    matrix = confusion_matrix(all_label, torch.squeeze(predict).float())
    avg_accuracy = (matrix.diagonal() / matrix.sum(axis=1)).mean()
    if args.da == 'pda':
        avg_accuracy = 0

    if args.distance == 'cosine':
        all_fea = torch.cat((all_fea, torch.ones(all_fea.size(0), 1)), 1)
        all_fea = (all_fea.t() / torch.norm(all_fea, p=2, dim=1)).t()

    all_fea = all_fea.float().cpu().numpy()
    K = all_output.size(1)
    aff = all_output.float().cpu().numpy()
    initc = aff.transpose().dot(all_fea)
    initc = initc / (1e-8 + aff.sum(axis=0)[:,None])

    dd = cdist(all_fea, initc, args.distance)
    dd[np.isnan(dd)] = np.inf
    pred_label = dd.argmin(axis=1)

    for round in range(1):
        aff = np.eye(K)[pred_label]
        initc = aff.transpose().dot(all_fea)
        initc = initc / (1e-8 + aff.sum(axis=0)[:,None])
        dd = cdist(all_fea, initc, args.distance)
        dd[np.isnan(dd)] = np.inf
        pred_label = dd.argmin(axis=1)

    acc = np.sum(pred_label == all_label.float().numpy()) / len(all_fea)
    matrix = confusion_matrix(all_label.float().numpy(), pred_label)
    avg_acc = (matrix.diagonal() / matrix.sum(axis=1)).mean()
    if args.da == 'pda':
        acc_list = ''
        avg_acc = 0
    log_str = 'Accuracy = {:.2f}% -> {:.2f}%    Per_class_accuracy = {:.2f}% -> {:.2f}%'.format(accuracy * 100, acc * 100, avg_accuracy * 100, avg_acc * 100)
    logging.info(log_str)

    # update labels with prior knowledge
    T = args.pk_temp
    probs = np.exp(-dd / T)
    probs = probs / probs.sum(1, keepdims=True)
    # first solve without smooth regularization
    pred_label_PK = pk_solver.solve_soft(probs)

    acc_PK = np.sum(pred_label_PK == all_label.float().numpy()) / len(all_fea)
    matrix_PK = confusion_matrix(all_label.float().numpy(), pred_label_PK)
    avg_acc_PK = (matrix_PK.diagonal() / matrix_PK.sum(axis=1)).mean()
    if args.da == 'pda':
        avg_acc_PK = 0
    log_str = 'PK Accuracy = {:.2f}% -> {:.2f}%    Per_class_accuracy = {:.2f}% -> {:.2f}%'.format(acc * 100, acc_PK * 100, avg_acc * 100, avg_acc_PK * 100)
    logging.info(log_str)

    # now solve with smooth regularization
    if args.pk_knn > 0:
        idx_unconf = np.where(pred_label_PK != pred_label)[0]
        knn_sample_idx = idx_unconf
        idx_conf = np.where(pred_label_PK == pred_label)[0]

        if len(idx_unconf) > 0 and len(idx_conf) > 0:
            # get knn of each samples
            dd_knn = cdist(all_fea[idx_unconf], all_fea[idx_conf], args.distance)
            knn_idx = []
            K = args.pk_knn
            for i in range(dd_knn.shape[0]):
                ind = np.argpartition(dd_knn[i], K)[:K]
                knn_idx.append(idx_conf[ind])

            knn_idx = np.stack(knn_idx, axis=0)
            knn_regs = list(zip(knn_sample_idx, knn_idx))
            pred_label_PK = pk_solver.solve_soft_knn_cst(probs, knn_regs=knn_regs)


        acc_PK = np.sum(pred_label_PK == all_label.float().numpy()) / len(all_fea)
        matrix_PK = confusion_matrix(all_label.float().numpy(), pred_label_PK)
        avg_acc_PK = (matrix_PK.diagonal() / matrix_PK.sum(axis=1)).mean()
        if args.da == 'pda':
            avg_acc_PK = 0
        log_str = 'PK Accuracy = {:.2f}% -> {:.2f}%    Per_class_accuracy = {:.2f}% -> {:.2f}%'.format(acc * 100, acc_PK * 100, avg_acc * 100, avg_acc_PK * 100)
        logging.info(log_str)

    return pred_label_PK.astype('int')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SHOT')
    parser.add_argument('--gpu_id', type=str, nargs='?', default='0', help="device id to run")
    parser.add_argument('--s', type=str, default=None, help="source")
    parser.add_argument('--t', type=str, default=None, help="target")
    parser.add_argument('--max_epoch', type=int, default=15, help="max iterations")
    parser.add_argument('--interval', type=int, default=15)
    parser.add_argument('--batch_size', type=int, default=64, help="batch_size")
    parser.add_argument('--worker', type=int, default=4, help="number of workers")
    parser.add_argument('--dset', type=str, default='office-home', choices=['visda-2017', 'domainnet40', 'office31', 'office-home', 'office-home-rsut', 'office-caltech'])
    parser.add_argument('--lr', type=float, default=1e-2, help="learning rate")
    parser.add_argument('--net', type=str, default='resnet50', help="alexnet, vgg16, resnet50, res101")
    parser.add_argument('--seed', type=int, default=2020, help="random seed")
 
    parser.add_argument('--gent', type=bool, default=True)
    parser.add_argument('--ent', type=bool, default=True)
    parser.add_argument('--threshold', type=int, default=0)
    parser.add_argument('--cls_par', type=float, default=0.3)
    parser.add_argument('--ent_par', type=float, default=1.0)
    parser.add_argument('--lr_decay1', type=float, default=0.1)
    parser.add_argument('--lr_decay2', type=float, default=1.0)

    parser.add_argument('--bottleneck', type=int, default=256)
    parser.add_argument('--epsilon', type=float, default=1e-5)
    parser.add_argument('--layer', type=str, default="wn", choices=["linear", "wn"])
    parser.add_argument('--classifier', type=str, default="bn", choices=["ori", "bn"])
    parser.add_argument('--distance', type=str, default='cosine', choices=["euclidean", "cosine"])  
    parser.add_argument('--output', type=str, default='san')
    parser.add_argument('--output_src', type=str, default='san')
    parser.add_argument('--da', type=str, default='uda', choices=['uda', 'pda'])
    parser.add_argument('--issave', type=bool, default=True)

    parser.add_argument('--timestamp', default=timestamp, type=str, help='timestamp')
    parser.add_argument('--use_file_logger', default='True', type=lambda x: bool(distutils.util.strtobool(x)),
                        help='whether use file logger')
    parser.add_argument('--names', default=[], type=list, help='names of tasks')
    parser.add_argument('--use_train_transform', default='False', type=lambda x: bool(distutils.util.strtobool(x)),
                        help='whether use train transform for label refinement')

    parser.add_argument('--pk_uconf', type=float, default=0.0)
    parser.add_argument('--pk_type', type=str, default="ub")
    parser.add_argument('--pk_allow', type=int, default=None)
    parser.add_argument('--pk_temp', type=float, default=1.0)
    parser.add_argument('--pk_prior_weight', type=float, default=10.)
    parser.add_argument('--pk_knn', type=int, default=1)
    parser.add_argument('--pk_NC', type=int, default=None)
    parser.add_argument('--pk_noise', type=float, default=0.0)
    parser.add_argument('--pk_dratio', type=float, default=1.0)
    parser.add_argument('--method', type=str, default="kshot")

    args = parser.parse_args()

    if args.dset == 'office-home':
        args.names = ['Art', 'Clipart', 'Product', 'Real_World']
        args.class_num = 65
    if args.dset == 'office-home-rsut':
        args.names = ['Clipart', 'Product', 'Real_World']
        args.class_num = 65
    if args.dset == 'domainnet40':
        args.names = ['sketch', 'clipart', 'painting', 'real']
        args.class_num = 40
    if args.dset == 'office31':
        args.names = ['webcam', 'amazon', 'dslr']
        args.class_num = 12
    if args.dset == 'visda-2017':
        args.names = ['train', 'validation']
        args.class_num = 12
    if args.dset == 'office-caltech':
        args.names = ['amazon', 'caltech', 'dslr', 'webcam']
        args.class_num = 10
        
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id
    resetRNGseed(args.seed)

    if args.dset == 'office-home-rsut':
        args.s += '_RS'

    dir = "{}_{}_{}_{}".format(args.timestamp, args.s, args.da, args.method)
    if args.use_file_logger:
        init_logger(dir, True, '../logs/SHOT/{}/'.format(args.method))
    logging.info("{}:{}".format(get_hostname(), get_pid()))

    for t in args.names:
        if t == args.s or t == args.s.split('_RS')[0]:
            continue
        args.t = t

        if args.dset == 'office-home-rsut':
            args.t += '_UT'

        folder = '../data/'
        args.s_dset_path = folder + args.dset + '/image_list/' + args.s + '.txt'
        args.t_dset_path = folder + args.dset + '/image_list/' + args.t + '.txt'
        args.test_dset_path = folder + args.dset + '/image_list/' + args.t + '.txt'

        if args.dset == 'domainnet40':
            args.s_dset_path = folder + args.dset + '/image_list/' + args.s + '_train_mini.txt'
            args.t_dset_path = folder + args.dset + '/image_list/' + args.t + '_train_mini.txt'
            args.test_dset_path = folder + args.dset + '/image_list/' + args.t + '_test_mini.txt'

        if args.dset == 'office-home':
            if args.da == 'pda':
                args.class_num = 65
                args.src_classes = [i for i in range(65)]
                args.tar_classes = [33, 32, 36, 15, 19, 2, 46, 49, 48, 53, 47, 54, 4, 18, 57, 23, 0, 45, 1, 38, 5, 13, 50, 11, 58]

        args.output_dir_src = "../checkpoints/SHOT/source/{}/".format(args.da)
        args.output_dir = "../checkpoints/SHOT/target_{}/".format(args.method)

        if not osp.exists(args.output_dir):
            os.system('mkdir -p ' + args.output_dir)
        if not osp.exists(args.output_dir):
            os.mkdir(args.output_dir)

        args.savename = 'par_' + str(args.cls_par)
        if args.da == 'pda':
            args.gent = ''
            args.savename = 'par_' + str(args.cls_par) + '_thr' + str(args.threshold)

        logging.info(print_args(args))
        train_target(args)
