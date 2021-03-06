from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

import sys
import os
import os.path as osp
import time
import datetime
import numpy as np
import cv2
from matplotlib import pyplot as plt

import torch
import torch.nn as nn
from torch.nn import functional as F
import torchvision
from torch.utils.tensorboard import SummaryWriter

import torchreid
from torchreid.utils import AverageMeter, visualize_ranked_results, save_checkpoint, re_ranking, mkdir_if_missing, visualize_ranked_activation_results, visualize_ranked_threshold_activation_results, visualize_ranked_mask_activation_results
from torchreid.losses import DeepSupervision
from torchreid import metrics


GRID_SPACING = 10
VECT_HEIGTH = 10


########
# visualize the training process
########
from visdom import Visdom

#########
# 創建可視覺結果:
#########
viz = Visdom()



class Engine(object):
    r"""A generic base Engine class for both image- and video-reid.

    Args:
        datamanager (DataManager): an instance of ``torchreid.data.ImageDataManager``
            or ``torchreid.data.VideoDataManager``.
        model (nn.Module): model instance.
        optimizer (Optimizer): an Optimizer.
        scheduler (LRScheduler, optional): if None, no learning rate decay will be performed.
        use_gpu (bool, optional): use gpu. Default is True.
    """

    def __init__(self, datamanager, model, optimizer=None, scheduler=None, use_gpu=True):
        self.datamanager = datamanager
        self.model = model
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.use_gpu = (torch.cuda.is_available() and use_gpu)
        self.writer = None

        # check attributes
        if not isinstance(self.model, nn.Module):
            raise TypeError('model must be an instance of nn.Module')

    def run(self, save_dir='log', max_epoch=0, start_epoch=0, fixbase_epoch=0, open_layers=None,
            start_eval=0, eval_freq=-1, test_only=False, print_freq=10,
            dist_metric='euclidean', normalize_feature=False, visrank=False, visrankactiv=False, visrankactivthr=False, maskthr=0.7, visrank_topk=10,
            use_metric_cuhk03=False, ranks=[1, 5, 10, 20], rerank=False, visactmap=False, vispartmap=False, visdrop=False, visdroptype='random'):
        r"""A unified pipeline for training and evaluating a model.

        Args:
            save_dir (str): directory to save model.
            max_epoch (int): maximum epoch.
            start_epoch (int, optional): starting epoch. Default is 0.
            fixbase_epoch (int, optional): number of epochs to train ``open_layers`` (new layers)
                while keeping base layers frozen. Default is 0. ``fixbase_epoch`` is counted
                in ``max_epoch``.
            open_layers (str or list, optional): layers (attribute names) open for training.
            start_eval (int, optional): from which epoch to start evaluation. Default is 0.
            eval_freq (int, optional): evaluation frequency. Default is -1 (meaning evaluation
                is only performed at the end of training).
            test_only (bool, optional): if True, only runs evaluation on test datasets.
                Default is False.
            print_freq (int, optional): print_frequency. Default is 10.
            dist_metric (str, optional): distance metric used to compute distance matrix
                between query and gallery. Default is "euclidean".
            normalize_feature (bool, optional): performs L2 normalization on feature vectors before
                computing feature distance. Default is False.
            visrank (bool, optional): visualizes ranked results. Default is False. It is recommended to
                enable ``visrank`` when ``test_only`` is True. The ranked images will be saved to
                "save_dir/visrank_dataset", e.g. "save_dir/visrank_market1501".
            visrank_topk (int, optional): top-k ranked images to be visualized. Default is 10.
            use_metric_cuhk03 (bool, optional): use single-gallery-shot setting for cuhk03.
                Default is False. This should be enabled when using cuhk03 classic split.
            ranks (list, optional): cmc ranks to be computed. Default is [1, 5, 10, 20].
            rerank (bool, optional): uses person re-ranking (by Zhong et al. CVPR'17).
                Default is False. This is only enabled when test_only=True.
            visactmap (bool, optional): visualizes activation maps. Default is False.
        """
        trainloader, testloader = self.datamanager.return_dataloaders()

        if visrank and not test_only:
            raise ValueError('visrank=True is valid only if test_only=True')

        if visrankactiv and not test_only:
            raise ValueError('visrankactiv=True is valid only if test_only=True')

        if visrankactivthr and not test_only:
            raise ValueError('visrankactivthr=True is valid only if test_only=True')

        if visdrop and not test_only:
            raise ValueError('visdrop=True is valid only if test_only=True')

        if test_only:
            self.test(
                0,
                testloader,
                dist_metric=dist_metric,
                normalize_feature=normalize_feature,
                visrank=visrank,
                visrankactiv=visrankactiv,
                visrank_topk=visrank_topk,
                save_dir=save_dir,
                use_metric_cuhk03=use_metric_cuhk03,
                ranks=ranks,
                rerank=rerank,
                maskthr=maskthr,
                visrankactivthr=visrankactivthr,
                visdrop=visdrop,
                visdroptype=visdroptype
            )
            return

        if self.writer is None:
            self.writer = SummaryWriter(log_dir=save_dir)

        if visactmap:
            self.visactmap(testloader, save_dir, self.datamanager.width, self.datamanager.height, print_freq)
            return

        if vispartmap:
            self.vispartmap(testloader, save_dir, self.datamanager.width, self.datamanager.height, print_freq)
            return

        time_start = time.time()
        print('=> Start training')
        #####
        # 初始化窗口 : Training loss:
        #####
        train_ALL_epoch_losses = viz.line([0.], [0], win='train_ALL_epoch_losses', opts=dict(title='train_All_epoch_losses',xlabel='epoch', ylabel= 'Loss',legend=['Train_epoch_loss']))       
        
        ######
        # Different loss output:
        ######
        Different_Losses = viz.line([[0.,0.,0.,0.,0.,0.]], [0], win='Different_Losses', opts=dict(title='Different_Losses',xlabel='epoch', ylabel= 'Loss',legend=['loss_t','loss_x', 'loss_db_x', 'loss_db_t',
                                                                                                                                                                  'loss_b_db_x', 'loss_b_db_t']))
        #######
        # 初始化窗口 (no re-rank)： mAP and rank1 v.s. loss 
        #######
        
        ALL_Loss_mAP_and_rank1 = viz.line([[0.,0.,0.]], [0], win='ALL_Loss_mAP_and_rank1', opts=dict(title='ALL_Loss_mAP_and_rank1',xlabel='epoch', ylabel= 'Accuracy',legend=['test_rank1','test_mAP', 'ALL_loss']))

        #######
        # 初始化窗口 (add re-rank)： mAP and rank1 v.s. loss 
        #######
        
        Re_rank_ALL_Loss_mAP_and_rank1 = viz.line([[0.,0.,0.]], [0], win='Re_rank_ALL_Loss_mAP_and_rank1', opts=dict(title='Re_rank_ALL_Loss_mAP_and_rank1',xlabel='epoch', ylabel= 'Accuracy',legend=['Re_test_rank1','Re_test_mAP', 'ALL_loss']))        
        #########
        # Training stage: 
        # --> 每個epoch位置
        #########
        # 總共的 loss:
        # loss, loss_t, loss_x, loss_db_x, loss_db_t, loss_b_db_x, loss_b_db_t
        for epoch in range(start_epoch, max_epoch):
            #self.train(epoch, max_epoch, trainloader, fixbase_epoch, open_layers, print_freq)
            loss_epoch_output, loss_t, loss_x, loss_db_x, loss_db_t, loss_b_db_x, loss_b_db_t = self.train(epoch, max_epoch, trainloader, fixbase_epoch, open_layers, print_freq)
            
            
            #if (epoch+1)>=start_eval and eval_freq>0 and (epoch+1)%eval_freq==0 and (epoch+1)!=max_epoch:
            if (epoch+1)>=start_eval and eval_freq>0 and (epoch+1)%eval_freq==0 and (epoch+1)!=max_epoch:
                rank1_org, mAP_org, rank1_re, mAP_re = self.test(
                    epoch,
                    testloader,
                    dist_metric=dist_metric,
                    normalize_feature=normalize_feature,
                    visrank=visrank,
                    visrankactiv=visrankactiv,
                    visrank_topk=visrank_topk,
                    save_dir=save_dir,
                    use_metric_cuhk03=use_metric_cuhk03,
                    ranks=ranks,
                    rerank=rerank,
                    maskthr=maskthr,
                    visrankactivthr=visrankactivthr
                ) 
                ######
                # 視覺化 training loss v.s. rank1 and mAP -- no-rank
                ######
                viz.line([[rank1_org,mAP_org,loss_epoch_output]], [epoch], win=ALL_Loss_mAP_and_rank1,update='append')
                ######
                # 視覺化 training loss v.s. rank1 and mAP -- re-rank
                ######
                viz.line([[rank1_re,mAP_re,loss_epoch_output]], [epoch], win=Re_rank_ALL_Loss_mAP_and_rank1,update='append')
                
                ######
                #self._save_checkpoint(epoch, rank1, save_dir)
                self._save_checkpoint(epoch, rank1_re, save_dir)
            if epoch == 0:
                rank1_org, mAP_org, rank1_re, mAP_re = self.test(
                    epoch,
                    testloader,
                    dist_metric=dist_metric,
                    normalize_feature=normalize_feature,
                    visrank=visrank,
                    visrankactiv=visrankactiv,
                    visrank_topk=visrank_topk,
                    save_dir=save_dir,
                    use_metric_cuhk03=use_metric_cuhk03,
                    ranks=ranks,
                    rerank=rerank,
                    maskthr=maskthr,
                    visrankactivthr=visrankactivthr
                ) 
                ######
                # 視覺化 training loss v.s. rank1 and mAP -- no re-rank
                ######
                viz.line([[rank1_org,mAP_org,loss_epoch_output]], [epoch], win=ALL_Loss_mAP_and_rank1,update='append')   
                ######
                # 視覺化 training loss v.s. rank1 and mAP -- re-rank
                ######
                viz.line([[rank1_re,mAP_re,loss_epoch_output]], [epoch], win=Re_rank_ALL_Loss_mAP_and_rank1,update='append')
            ######
            # 視覺化 training loss at all epoch:
            ######
            viz.line([loss_epoch_output], [epoch], win=train_ALL_epoch_losses,update='append')
            ######
            # 視覺化 different loss at all epoch
            ######
            viz.line([[loss_t, loss_x, loss_db_x, loss_db_t, loss_b_db_x, loss_b_db_t]], [epoch], win=Different_Losses,update='append')

            
        if max_epoch > 0:
            print('=> Final test')
            rank1_org, mAP_org, rank1_re, mAP_re = self.test(
                epoch,
                testloader,
                dist_metric=dist_metric,
                normalize_feature=normalize_feature,
                visrank=visrank,
                visrankactiv=visrankactiv,
                visrank_topk=visrank_topk,
                save_dir=save_dir,
                use_metric_cuhk03=use_metric_cuhk03,
                ranks=ranks,
                rerank=rerank,
                maskthr=maskthr,
                visrankactivthr=visrankactivthr
            )
            self._save_checkpoint(epoch, rank1_re, save_dir)

        elapsed = round(time.time() - time_start)
        elapsed = str(datetime.timedelta(seconds=elapsed))
        print('Elapsed {}'.format(elapsed))
        if self.writer is None:
            self.writer.close()

    def train(self):
        r"""Performs training on source datasets for one epoch.

        This will be called every epoch in ``run()``, e.g.

        .. code-block:: python
            
            for epoch in range(start_epoch, max_epoch):
                self.train(some_arguments)

        .. note::
            
            This must be implemented in subclasses.
        """
        raise NotImplementedError

    def test(self, epoch, testloader, dist_metric='euclidean', normalize_feature=False,
             visrank=False, visrankactiv = False, visrank_topk=10, save_dir='', use_metric_cuhk03=False,
             ranks=[1, 5, 10, 20], rerank=False, maskthr=0.7, visrankactivthr=False, visdrop=False, visdroptype = 'random'):
        r"""Tests model on target datasets.

        .. note::

            This function has been called in ``run()``.

        .. note::

            The test pipeline implemented in this function suits both image- and
            video-reid. In general, a subclass of Engine only needs to re-implement
            ``_extract_features()`` and ``_parse_data_for_eval()`` (most of the time),
            but not a must. Please refer to the source code for more details.
        """
        targets = list(testloader.keys())
        
        for name in targets:
            domain = 'source' if name in self.datamanager.sources else 'target'
            print('##### Evaluating {} ({}) #####'.format(name, domain))
            queryloader = testloader[name]['query']
            galleryloader = testloader[name]['gallery']
            rank1_org, mAP_org, rank1_re, mAP_re = self._evaluate(
                epoch,
                dataset_name=name,
                queryloader=queryloader,
                galleryloader=galleryloader,
                dist_metric=dist_metric,
                normalize_feature=normalize_feature,
                visrank=visrank,
                visrankactiv=visrankactiv,
                visrank_topk=visrank_topk,
                save_dir=save_dir,
                use_metric_cuhk03=use_metric_cuhk03,
                ranks=ranks,
                rerank=rerank,
                maskthr=maskthr,
                visrankactivthr=visrankactivthr,
                visdrop=visdrop,
                visdroptype=visdroptype
            )
        # 回傳 rank1結果
        #return rank1
        # 回傳 rank1 和 mAP
        # return rank 1
        #return cmc[0]
        # return rank 1 and mAP
        #####
        # no re-rank:
        # 1. cmc_org
        # 2. mAP_org
        #####
        #####
        # re-rank:
        # 1. cmc_re
        # 2. mAP_re
        ##### 
        return rank1_org, mAP_org, rank1_re, mAP_re

    @torch.no_grad()
    def _evaluate(self, epoch, dataset_name='', queryloader=None, galleryloader=None,
                  dist_metric='euclidean', normalize_feature=False, visrank=False, visrankactiv = False,
                  visrank_topk=10, save_dir='', use_metric_cuhk03=False, ranks=[1, 5, 10, 20],
                  rerank=False, visrankactivthr = False, maskthr=0.7, visdrop=False, visdroptype='random'):
        batch_time = AverageMeter()

        print('Extracting features from query set ...')
        qf, qa, q_pids, q_camids, qm = [], [], [], [], [] # query features, query activations, query person IDs, query camera IDs and image drop masks
        for _, data in enumerate(queryloader):
            imgs, pids, camids = self._parse_data_for_eval(data)
            if self.use_gpu:
                imgs = imgs.cuda()
            end = time.time()
            features = self._extract_features(imgs)
            activations = self._extract_activations(imgs)
            dropmask = self._extract_drop_masks(imgs, visdrop, visdroptype)
            batch_time.update(time.time() - end)
            features = features.data.cpu()
            qf.append(features)
            qa.append(torch.Tensor(activations))
            qm.append(torch.Tensor(dropmask))
            q_pids.extend(pids)
            q_camids.extend(camids)
        qf = torch.cat(qf, 0)
        qm = torch.cat(qm, 0)
        qa = torch.cat(qa, 0)
        q_pids = np.asarray(q_pids)
        q_camids = np.asarray(q_camids)
        print('Done, obtained {}-by-{} matrix'.format(qf.size(0), qf.size(1)))

        print('Extracting features from gallery set ...')
        gf, ga, g_pids, g_camids, gm = [], [], [], [], [] # gallery features, gallery activations,  gallery person IDs, gallery camera IDs and image drop masks
        end = time.time()
        for _, data in enumerate(galleryloader):
            imgs, pids, camids = self._parse_data_for_eval(data)
            if self.use_gpu:
                imgs = imgs.cuda()
            end = time.time()
            features = self._extract_features(imgs)
            activations = self._extract_activations(imgs)
            dropmask = self._extract_drop_masks(imgs, visdrop, visdroptype)
            batch_time.update(time.time() - end)
            features = features.data.cpu()
            gf.append(features)
            ga.append(torch.Tensor(activations))
            gm.append(torch.Tensor(dropmask))
            g_pids.extend(pids)
            g_camids.extend(camids)
        gf = torch.cat(gf, 0)
        gm = torch.cat(gm, 0)
        ga = torch.cat(ga, 0)
        g_pids = np.asarray(g_pids)
        g_camids = np.asarray(g_camids)
        print('Done, obtained {}-by-{} matrix'.format(gf.size(0), gf.size(1)))

        print('Speed: {:.4f} sec/batch'.format(batch_time.avg))

        if normalize_feature:
            print('Normalzing features with L2 norm ...')
            qf = F.normalize(qf, p=2, dim=1)
            gf = F.normalize(gf, p=2, dim=1)

        print('Computing distance matrix with metric={} ...'.format(dist_metric))
        distmat = metrics.compute_distance_matrix(qf, gf, dist_metric)
        distmat = distmat.numpy()

        #always show results without re-ranking first
        print('Computing CMC and mAP ...')
        cmc_org, mAP_org = metrics.evaluate_rank(
            distmat,
            q_pids,
            g_pids,
            q_camids,
            g_camids,
            use_metric_cuhk03=use_metric_cuhk03
        )

        print('** Results **')
        print('mAP: {:.1%}'.format(mAP_org))
        print('CMC curve')
        for r in ranks:
            print('Rank-{:<3}: {:.1%}'.format(r, cmc_org[r-1]))

        if rerank:
            print('Applying person re-ranking ...')
            distmat_qq = metrics.compute_distance_matrix(qf, qf, dist_metric)
            distmat_gg = metrics.compute_distance_matrix(gf, gf, dist_metric)
            distmat = re_ranking(distmat, distmat_qq, distmat_gg)
            print('Computing CMC and mAP ...')
            cmc_re, mAP_re = metrics.evaluate_rank(
                distmat,
                q_pids,
                g_pids,
                q_camids,
                g_camids,
                use_metric_cuhk03=use_metric_cuhk03
            )

            print('** Results with Re-Ranking**')
            print('mAP: {:.1%}'.format(mAP_re))
            print('CMC curve')
            for r in ranks:
                print('Rank-{:<3}: {:.1%}'.format(r, cmc_re[r-1]))


        if visrank:
            visualize_ranked_results(
                distmat,
                self.datamanager.return_testdataset_by_name(dataset_name),
                self.datamanager.data_type,
                width=self.datamanager.width,
                height=self.datamanager.height,
                save_dir=osp.join(save_dir, 'visrank_'+dataset_name),
                topk=visrank_topk
            )
        if visrankactiv:
            visualize_ranked_activation_results(
                distmat,
                qa,
                ga,
                self.datamanager.return_testdataset_by_name(dataset_name),
                self.datamanager.data_type,
                width=self.datamanager.width,
                height=self.datamanager.height,
                save_dir=osp.join(save_dir, 'visrankactiv_'+dataset_name),
                topk=visrank_topk
            )
        if visrankactivthr:
            visualize_ranked_threshold_activation_results(
                distmat,
                qa,
                ga,
                self.datamanager.return_testdataset_by_name(dataset_name),
                self.datamanager.data_type,
                width=self.datamanager.width,
                height=self.datamanager.height,
                save_dir=osp.join(save_dir, 'visrankactivthr_'+dataset_name),
                topk=visrank_topk,
                threshold=maskthr
            )
        if visdrop:
            visualize_ranked_mask_activation_results(
                distmat,
                qa,
                ga,
                qm,
                gm,
                self.datamanager.return_testdataset_by_name(dataset_name),
                self.datamanager.data_type,
                width=self.datamanager.width,
                height=self.datamanager.height,
                save_dir=osp.join(save_dir, 'visdrop_{}_{}'.format(visdroptype, dataset_name)),
                topk=visrank_topk
            )
        
        # return rank 1
        #return cmc[0]
        # return rank 1 and mAP
        #####
        # no re-rank:
        # 1. cmc_org
        # 2. mAP_org
        #####
        #####
        # re-rank:
        # 1. cmc_re
        # 2. mAP_re
        #####        
        
        return cmc_org[0], mAP_org, cmc_re[0], mAP_re

    @torch.no_grad()
    def visactmap(self, testloader, save_dir, width, height, print_freq):
        """Visualizes CNN activation maps to see where the CNN focuses on to extract features.

        This function takes as input the query images of target datasets

        Reference:
            - Zagoruyko and Komodakis. Paying more attention to attention: Improving the
              performance of convolutional neural networks via attention transfer. ICLR, 2017
            - Zhou et al. Omni-Scale Feature Learning for Person Re-Identification. ICCV, 2019.
        """
        self.model.eval()
        
        imagenet_mean = [0.485, 0.456, 0.406]
        imagenet_std = [0.229, 0.224, 0.225]

        for target in list(testloader.keys()):
            queryloader = testloader[target]['query']
            # original images and activation maps are saved individually
            actmap_dir = osp.join(save_dir, 'actmap_'+target)
            mkdir_if_missing(actmap_dir)
            print('Visualizing activation maps for {} ...'.format(target))

            for batch_idx, data in enumerate(queryloader):
                imgs, paths = data[0], data[3]
                if self.use_gpu:
                    imgs = imgs.cuda()
                
                # forward to get convolutional feature maps
                try:
                    outputs = self.model(imgs, return_featuremaps=True)
                except TypeError:
                    raise TypeError('forward() got unexpected keyword argument "return_featuremaps". ' \
                                    'Please add return_featuremaps as an input argument to forward(). When ' \
                                    'return_featuremaps=True, return feature maps only.')
                
                if outputs.dim() != 4:
                    raise ValueError('The model output is supposed to have ' \
                                     'shape of (b, c, h, w), i.e. 4 dimensions, but got {} dimensions. '
                                     'Please make sure you set the model output at eval mode '
                                     'to be the last convolutional feature maps'.format(outputs.dim()))
                
                # compute activation maps
                outputs = (outputs**2).sum(1)
                b, h, w = outputs.size()
                outputs = outputs.view(b, h*w)
                outputs = F.normalize(outputs, p=2, dim=1)
                outputs = outputs.view(b, h, w)
                
                if self.use_gpu:
                    imgs, outputs = imgs.cpu(), outputs.cpu()

                for j in range(outputs.size(0)):
                    # get image name
                    path = paths[j]
                    imname = osp.basename(osp.splitext(path)[0])
                    
                    # RGB image
                    img = imgs[j, ...]
                    for t, m, s in zip(img, imagenet_mean, imagenet_std):
                        t.mul_(s).add_(m).clamp_(0, 1)
                    img_np = np.uint8(np.floor(img.numpy() * 255))
                    img_np = img_np.transpose((1, 2, 0)) # (c, h, w) -> (h, w, c)
                    
                    # activation map
                    am = outputs[j, ...].numpy()
                    am = cv2.resize(am, (width, height))
                    am = 255 * (am - np.max(am)) / (np.max(am) - np.min(am) + 1e-12)
                    am = np.uint8(np.floor(am))
                    am = cv2.applyColorMap(am, cv2.COLORMAP_JET)
                    
                    # overlapped
                    overlapped = img_np * 0.4 + am * 0.6
                    overlapped[overlapped>255] = 255
                    overlapped = overlapped.astype(np.uint8)

                    # save images in a single figure (add white spacing between images)
                    # from left to right: original image, activation map, overlapped image
                    grid_img = 255 * np.ones((height, 3*width+2*GRID_SPACING, 3), dtype=np.uint8)
                    grid_img[:, :width, :] = img_np[:, :, ::-1]
                    grid_img[:, width+GRID_SPACING: 2*width+GRID_SPACING, :] = am
                    grid_img[:, 2*width+2*GRID_SPACING:, :] = overlapped
                    cv2.imwrite(osp.join(actmap_dir, imname+'.jpg'), grid_img)

                if (batch_idx+1) % print_freq == 0:
                    print('- done batch {}/{}'.format(batch_idx+1, len(queryloader)))

    @torch.no_grad()
    def vispartmap(self, testloader, save_dir, width, height, print_freq):
        """Visualizes CNN activation maps to see where the CNN focuses on to extract features.

        This function takes as input the query images of target datasets

        Reference:
            - Zagoruyko and Komodakis. Paying more attention to attention: Improving the
              performance of convolutional neural networks via attention transfer. ICLR, 2017
            - Zhou et al. Omni-Scale Feature Learning for Person Re-Identification. ICCV, 2019.
        """
        self.model.eval()
        
        imagenet_mean = [0.485, 0.456, 0.406]
        imagenet_std = [0.229, 0.224, 0.225]

        for target in list(testloader.keys()):
            queryloader = testloader[target]['query']
            # original images and activation maps are saved individually
            actmap_dir = osp.join(save_dir, 'partmap_'+target)
            mkdir_if_missing(actmap_dir)
            print('Visualizing parts activation maps for {} ...'.format(target))

            for batch_idx, data in enumerate(queryloader):
                imgs, paths = data[0], data[3]
                if self.use_gpu:
                    imgs = imgs.cuda()

                # forward to get convolutional feature maps
                try:
                    outputs_list = self.model(imgs, return_partmaps=True)
                except TypeError:
                    raise TypeError('forward() got unexpected keyword argument "return_partmaps". ' \
                                    'Please add return_partmaps as an input argument to forward(). When ' \
                                    'return_partmaps=True, return feature maps only.')
                if outputs_list[0][0].dim() != 4:
                    raise ValueError('The model output is supposed to have ' \
                                     'shape of (b, c, h, w), i.e. 4 dimensions, but got {} dimensions. '
                                     'Please make sure you set the model output at eval mode '
                                     'to be the last convolutional feature maps'.format(outputs_list[0][0].dim()))


                #print stats between parts and weights
                print("First image stats")
                w = []
                for i, (_, _, _, weights) in enumerate(outputs_list):
                    print("\tpart{} min {} max {}".format(i, torch.min(weights[0, ...]), torch.max(weights[0, ...])))
                    w.append(weights)
                print("Second image stats")
                for i, (_, _, _, weights) in enumerate(outputs_list):
                    print("\tpart{} min {} max {}".format(i, torch.min(weights[1, ...]), torch.max(weights[1, ...])))
                print("Difference")
                for i, (_, _, _, weights) in enumerate(outputs_list):
                    print("\tpart{} min {} max {} mean {}".format(i, torch.min(weights[0, ...] - weights[1, ...]), torch.max(weights[0, ...] - weights[1, ...]), torch.mean(weights[0, ...] - weights[1, ...])))
                print("\tbetween min {} max {} mean {}".format(torch.min(w[0] - w[1]), torch.max(w[0] - w[1]), torch.mean(w[0] - w[1])))

                for part_ind, (outputs, weights, _, _) in enumerate(outputs_list):
                    # compute activation maps
                    b, c, h, w = outputs.size()
                    outputs = (outputs**2).sum(1)
                    outputs = outputs.view(b, h*w)
                    outputs = F.normalize(outputs, p=2, dim=1)
                    outputs = outputs.view(b, h, w)

                    weights = weights.view(b, c)
                    weights = F.normalize(weights, p=2, dim=1)
                    weights = weights.view(b, 1, c)

                    if self.use_gpu:
                        imgs, outputs, weights = imgs.cpu(), outputs.cpu(), weights.cpu()

                    for j in range(outputs.size(0)):
                        # get image name
                        path = paths[j]
                        imname = osp.basename(osp.splitext(path)[0])

                        # RGB image
                        img = imgs[j, ...].clone()
                        for t, m, s in zip(img, imagenet_mean, imagenet_std):
                            t.mul_(s).add_(m).clamp_(0, 1)
                        img_np = np.uint8(np.floor(img.numpy() * 255))
                        img_np = img_np.transpose((1, 2, 0)) # (c, h, w) -> (h, w, c)
                        
                        # activation map
                        am = outputs[j, ...].numpy()
                        am = cv2.resize(am, (width, height))
                        am = 255 * (am - np.max(am)) / (np.max(am) - np.min(am) + 1e-12)
                        am = np.uint8(np.floor(am))
                        am = cv2.applyColorMap(am, cv2.COLORMAP_JET)

                        #parts activation map
                        pam = weights[j, ...].numpy()
                        pam = np.resize(pam, (VECT_HEIGTH, c)) #expand to create larger vectors for better visuallization
                        pam = cv2.resize(pam, (3*width+2*GRID_SPACING, VECT_HEIGTH))
                        pam = 255 * (pam - np.max(pam)) / (np.max(pam) - np.min(pam) + 1e-12)
                        pam = np.uint8(np.floor(pam))
                        pam = cv2.applyColorMap(pam, cv2.COLORMAP_JET)

                        # overlapped
                        overlapped = img_np * 0.4 + am * 0.6
                        overlapped[overlapped>255] = 255
                        overlapped = overlapped.astype(np.uint8)

                        # save images in a single figure (add white spacing between images)
                        # from left to right: original image, activation map, overlapped image
                        grid_img = 255 * np.ones((height + GRID_SPACING + VECT_HEIGTH, 3*width+2*GRID_SPACING, 3), dtype=np.uint8)
                        grid_img[:height, :width, :] = img_np[:, :, ::-1]
                        grid_img[:height, width+GRID_SPACING: 2*width+GRID_SPACING, :] = am
                        grid_img[:height, 2*width+2*GRID_SPACING:, :] = overlapped
                        grid_img[height + GRID_SPACING:, :, :] = pam

                        cv2.imwrite(osp.join(actmap_dir, imname+'_{}.jpg'.format(part_ind)), grid_img)

                    if (batch_idx+1) % print_freq == 0:
                        print('- done batch {}/{} part {}/{}'.format(batch_idx+1, len(queryloader), part_ind + 1, len(outputs_list)))

    def _compute_loss(self, criterion, outputs, targets):
        if isinstance(outputs, (tuple, list)):
            loss = DeepSupervision(criterion, outputs, targets)
        else:
            loss = criterion(outputs, targets)
        return loss

    def _extract_features(self, input):
        self.model.eval()
        return self.model(input)

    def _extract_activations(self, input):
        self.model.eval()
        outputs = self.model(input, return_featuremaps=True)
        outputs = (outputs**2).sum(1)
        b, h, w = outputs.size()
        outputs = outputs.view(b, h*w)
        outputs = F.normalize(outputs, p=2, dim=1)
        outputs = outputs.view(b, h, w)
        activations = []
        for j in range(outputs.size(0)):
            # activation map
            am = outputs[j, ...].cpu().numpy()
            am = cv2.resize(am, (self.datamanager.width, self.datamanager.height))
            am = 255 * (am - np.max(am)) / (np.max(am) - np.min(am) + 1e-12)
            activations.append(am)
        return np.array(activations)

    def _extract_drop_masks(self, input, visdrop, visdroptype):
        self.model.eval()
        drop_top = (visdroptype == 'top')
        outputs = self.model(input, drop_top=drop_top, visdrop=visdrop)
        outputs = outputs.mean(1)
        masks = []
        for j in range(outputs.size(0)):
            # drop masks
            dm = outputs[j, ...].cpu().numpy()
            dm = cv2.resize(dm, (self.datamanager.width, self.datamanager.height))
            masks.append(dm)
        return np.array(masks)

    def _parse_data_for_train(self, data):
        imgs = data[0]
        pids = data[1]
        return imgs, pids

    def _parse_data_for_eval(self, data):
        imgs = data[0]
        pids = data[1]
        camids = data[2]
        return imgs, pids, camids

    def _save_checkpoint(self, epoch, rank1, save_dir, is_best=False):
        save_checkpoint({
            'state_dict': self.model.state_dict(),
            'epoch': epoch + 1,
            'rank1': rank1,
            'optimizer': self.optimizer.state_dict(),
        }, save_dir, is_best=is_best)
