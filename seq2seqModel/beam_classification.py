import tensorflow as tf
import math
import numpy as np

g_2 = tf.Graph()

def run_beam_classification(sess,features,labels,beam_size,save_path=None,inference=False, load_params_path=None,reuse=False):
    batch_size = 8
    input_index = 0
    sentence_num = len(labels)
    feat_length = len(features[0][0])
    learning_rate = 0.01
    hidden_layer_size = 50

    #tf.reset_default_graph()
    with tf.variable_scope("classification", reuse=reuse):
        #with g_2.as_default():
        # input placeholders
        feats_placeholder = tf.placeholder(tf.float32, shape=(beam_size,feat_length))
        labels_placeholder = tf.placeholder(tf.float32, shape=(beam_size,1))

        # trainable variables
        weights1 = tf.get_variable("weights1", shape=[feat_length, hidden_layer_size],
                              initializer=tf.contrib.layers.xavier_initializer())
        weights2 = tf.get_variable("weights2", shape=[hidden_layer_size, hidden_layer_size],
                                   initializer=tf.contrib.layers.xavier_initializer())
        weights3 = tf.get_variable("weights3", shape=[hidden_layer_size, 1],
                                   initializer=tf.contrib.layers.xavier_initializer())
        biases1 = tf.get_variable("biases1", shape=[hidden_layer_size],
        initializer=tf.constant_initializer(0.0))
        biases2 = tf.get_variable("biases2", shape=[hidden_layer_size],
        initializer=tf.constant_initializer(0.0))
        biases3 = tf.get_variable("biases3", shape=[beam_size,1],
        initializer=tf.constant_initializer(0.0))

        hidden1 = tf.nn.relu(tf.matmul(feats_placeholder, weights1) + biases1)
        hidden2 = tf.nn.relu(tf.matmul(hidden1, weights2) + biases2)
        logits = tf.matmul(hidden2, weights3) + biases3


        # loss function
        theta = tf.trainable_variables()[:6]
        saver = tf.train.Saver(theta)
        logits = tf.reshape(logits,(1,beam_size))
        labels_cur = tf.reshape(labels_placeholder,(1,40))
        cross_entropy_this = tf.nn.softmax_cross_entropy_with_logits(
            labels=labels_cur, logits=logits, name='xentropy')
        this_loss = tf.reduce_mean(cross_entropy_this, name='xentropy_mean')

        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
        compute_program_grads_this = optimizer.compute_gradients(this_loss)
        w1grad = tf.placeholder(tf.float32, name="w1grad")
        w2grad = tf.placeholder(tf.float32, name="w2grad")
        w3grad = tf.placeholder(tf.float32, name="w3grad")
        b1grad = tf.placeholder(tf.float32, name="b1grad")
        b2grad = tf.placeholder(tf.float32, name="b2grad")
        b3grad = tf.placeholder(tf.float32, name="b3grad")
        batch_grad = [w1grad,b1grad,w2grad,b2grad,w3grad,b3grad]
        update_grads = optimizer.apply_gradients(zip(batch_grad, theta))

        if inference:
            saver.restore(sess, load_params_path)
        else:
            init = tf.global_variables_initializer()
            sess.run(init)
        gradList = sess.run(theta)  # just to get dimensions right
        gradBuffer = {}
        for i, grad in enumerate(gradList):
            gradBuffer[i] = grad * 0
        sum_loss=0
        total=0
        if not inference:
            for epoch in range(15):
                input_index = 0
                while input_index+batch_size < sentence_num:
                    #print("step: ", input_index)
                    batch_features = features[input_index: input_index + batch_size]
                    batch_labels = labels[input_index: input_index + batch_size]
                    diffs = []
                    for j in range(len(batch_features)):
                        # pad with zeros beams with less then k programs

                        diff = beam_size - len(batch_features[j])
                        diffs.append(diff)
                        for i in range(beam_size - len(batch_features[j])):
                            batch_features[j].append([-100]+[0]*(feat_length-1))
                            batch_labels[j].append(0)
                    for i in range(len(batch_labels)):
                        batch_labels[i] = np.array(batch_labels[i])
                        if np.sum(batch_labels[i]) > 0:
                            batch_labels[i] = batch_labels[i] / np.sum(batch_labels[i])
                            #batch_labels[i] += 0.00000001

                    input_index += batch_size
                    index_in_batch = 0
                    while index_in_batch < batch_size:

                        if np.sum(batch_labels[index_in_batch]) < 1:
                            index_in_batch += 1
                            #print("dropped")
                            continue
                        feed_dict = {labels_placeholder: np.reshape(batch_labels[index_in_batch],(beam_size,1)),
                                     feats_placeholder: batch_features[index_in_batch]}

                        probs,  ce = sess.run([logits,cross_entropy_this],feed_dict=feed_dict)
                        #print("probs:",probs)
                        #if input_index > 100:"classification/xentropy_mean"
                        params = sess.run(theta)
                        loss_cur, program_grad = sess.run([this_loss,compute_program_grads_this], feed_dict=feed_dict)
                        sum_loss += loss_cur
                        total +=1
                        for var, grad in enumerate(program_grad):
                            gradBuffer[var] += grad[0]

                        index_in_batch += 1
                    sess.run(update_grads, feed_dict={g: gradBuffer[i] for i, g in enumerate(batch_grad)})
                    for var, grad in enumerate(gradBuffer):
                        gradBuffer[var] = gradBuffer[var] * 0
                    print("average loss: ", sum_loss/total)
                    sum_loss = 0
                    total = 0


            if save_path:
                saver.save(sess, save_path)
            return

        original_len = len(features[0])
        for i in range(beam_size - original_len):
            features[0].append([0] * feat_length)
            labels[0].append(0)
        labels[0] = np.array(labels[0])
        if np.sum(labels[0]) > 0:
            labels[0] = labels[0] / np.sum(labels[0])
        labels[0] = np.reshape(labels[0],(beam_size,1))
        probs = sess.run([logits], feed_dict={feats_placeholder:features[0]})#, labels_placeholder:labels[0]
        result = np.argmax(probs[:original_len])
        print(result)
    return result

