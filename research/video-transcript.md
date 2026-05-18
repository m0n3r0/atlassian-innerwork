# Video Transcript: Atlassian Edge Platform Retrospective

Source: https://www.youtube.com/watch?v=55pTFVoclvE

```text
[0.00] I was recently affected by the layoffs
[3.48] made by Atlassian and I wanted to take
[6.32] some time out to reflect on the time
[9.08] that I spent working for Atlassian. I
[11.44] worked there for about eight years.
[13.72] During that time I built a lot of things
[16.20] and I wanted to talk about what I built,
[18.00] mainly the things that I personally
[19.80] found interesting or that I'm proud of.
[21.92] I hope that this video will be useful or
[24.52] helpful to someone who perhaps is or was
[28.40] in the same situation as me and maybe
[31.04] it'll give them some inspiration in
[32.68] terms of how they can tackle the same
[35.00] things that I did or something similar
[37.60] and perhaps avoid some of the mistakes
[39.44] that I've made. I also might talk about
[41.28] non-technical parts of my experience at
[43.96] Atlassian, although most of it will be
[45.56] technical and this video will be split
[48.00] into chapters so that you can skip to
[51.52] sections that are more interesting to
[54.20] you rather than rather than watching the
[56.00] video from start to finish. So I suppose
[58.52] to start with I'll talk about when I was
[60.44] first hired and even though I it was
[62.88] eight years ago, I still remember the
[64.96] interview process, which is different
[67.00] nowadays, and the reason why I was hired
[70.12] or at least from my perspective the
[71.64] reason why I was hired and the things
[73.48] that I started working on during the
[75.16] start. So yeah, let's just start at the
[78.28] interview process. So I was interviewed
[80.64] by some people that I now consider
[83.24] friends and I remember having the
[85.08] impression while being interviewed that
[88.04] these individuals were quite intelligent
[90.68] and that was something that was exciting
[92.20] for me. The interview process consisted
[93.84] of a coding quiz on HackerRank, which I
[96.80] aced with full marks. Then the first
[99.32] technical interview was with two
[102.28] interviewers and they gave me a white
[104.84] paper and asked me to read it while they
[106.96] sat out of the room for about 10
[108.72] minutes. They came back in and then
[110.52] asked me questions about the white
[112.68] paper, asked me to basically articulate
[114.68] what was in in white paper and the white
[116.76] paper was actually about custom domains,
[119.32] and the white paper was by Cloudflare.
[121.12] They then asked me a few questions about
[123.60] things like microservices and
[125.76] architectural things like that, um
[127.80] containers and and whatnot. And they
[129.92] were happy enough. I don't remember the
[131.48] rest, but they were happy enough with
[133.72] with me during that stage, so I
[135.56] continued to the uh second technical
[138.08] interview, which was a troubleshooting
[139.44] exercise where I was asked to
[142.40] essentially prompt the interviewer for
[144.40] information in order to troubleshoot a
[147.12] real incident that occurred in
[148.80] Atlassian. And it was a it was an
[150.56] application problem that lead led to a
[154.04] denial of service. Uh so that was fun.
[156.60] And then I think I was asked something
[158.60] about how um latency-based DNS works,
[162.40] and my answer was not accurate, but
[165.72] perhaps acceptable. I I I thought about
[168.12] it from first principles, and I thought
[169.84] that that's uh for example, I thought
[172.20] that Route 53 did a triangulation based
[174.76] on the actual latency of the client, but
[178.08] it is more like that they use a uh they
[181.64] probably use a geolocation database in
[184.32] order to do latency-based routing of DNS
[187.40] requests of the DNS answers, sorry. Then
[190.24] after that was a values uh interview.
[192.84] And to be honest, I don't really
[194.00] remember most of the questions for for
[196.28] the values portion, but
[198.52] I do remember one thing, which was when
[201.64] I asked the question of I asked I asked
[204.56] the interviewers to think about 12
[206.48] months from now and to look back
[208.12] retrospectively, what is the thing that
[210.40] I would have had to achieve in order to
[213.00] for for you to say it was a good
[215.04] decision hiring this person. And then
[216.80] they told me about
[218.76] a [clears throat]
[219.44] an application that they needed to be
[221.68] built for the platform within Atlassian,
[224.88] and the application would facilitate
[227.04] self-service load balancers. Sort of
[228.80] similar to if you were using Amazon
[232.00] application load balances or the
[234.08] equivalent in any cloud provider. But
[235.88] for the internal developers of
[238.36] Atlassian. And it was essentially just a
[240.88] a framework that I personally was not
[243.00] familiar with. And I said I could build
[245.32] it because I had confidence in building
[247.68] web apps with Python at that time. And
[250.48] they accepted my level of confidence and
[253.00] decided to hire me. So that's the the
[254.92] interview portion completed. So I joined
[257.44] Atlassian and they have this classic
[260.48] saying or impression that when you join
[263.64] Atlassian that you are drinking from the
[266.16] fire hose because there's so much
[268.16] information that you have to absorb in
[270.32] the first few weeks and months in order
[272.68] to just sort of get going. My first my
[275.64] very first task that at least task that
[278.00] I gave myself was to build the
[280.92] application that they had told me that
[283.36] they wanted. Let me just open a browser
[285.80] and we'll take a little looky at what I
[288.56] mean exactly. Let me just uh move my
[291.04] face a little bit. There's more real
[292.84] estate. Now obviously it's scalar draw
[295.16] is not what I care about. So they wanted
[297.40] me to build an open service broker. This
[299.52] is
[300.52] a a web app with an API which
[302.36] facilitates the provisioning of
[304.76] resources for a platform essentially. So
[307.12] you can you can see here
[309.48] it's sort of built to operate in a
[311.84] Kubernetes world where you're submitting
[313.92] these provisioning requests as things
[317.60] come up and down. And it's going to bind
[320.20] a resource to your pod or your cloud
[323.08] instance or whatever it is as you can
[325.28] see here. And it sort of sits in between
[328.08] these real resources. So you might
[331.64] provision something like a database and
[334.20] then you'll get MySQL. So you'll get
[336.12] something that's SQL compatible but
[338.08] that's abstracted away for your internal
[340.16] developers. Anyhow,
[342.56] the spec is uh, is here on GitHub. You
[346.52] can take a look at it. It goes into It
[348.56] goes into, like, for example, the
[351.76] catalog endpoint. And the catalog lists
[354.44] all of the services and plans that are
[356.88] available on the OSB, and, uh, just
[360.32] metadata about them. And you might say
[363.52] query the the service broker and then
[365.96] display some of the metadata in your
[368.44] Maybe you've got a a a console a
[370.28] console, like, the Amazon console, but
[372.80] maybe you've got something like that
[373.96] internally. Where developers can click
[376.40] and provision things. In the Atlassian
[378.08] case, it was all through configuration
[380.44] files that were committed to, um,
[383.00] version control, and then those would be
[385.04] uploaded, uh, during uploaded from a a
[387.84] build server to deploy a service. Um,
[390.60] but, yeah. So, you might have, you know,
[392.88] other APIs like, uh, provisioning here.
[395.64] So, put and patch for updating and
[398.32] deletes and blah blah blah. So, you
[400.12] would just basically go ahead and and
[401.84] implement this. Or
[403.48] I mean, if you wanted to build your own,
[405.16] and that is essentially what I did. You
[407.08] can see also there's a an open API
[409.12] document here that has the endpoints.
[412.08] So, I chose to build this in in Python
[414.76] using Flask. Oh, no. In fact, what I
[417.80] What I built it with first is with a
[420.68] library called Connection. This is a
[422.64] Python library which takes an open API
[425.88] document and then creates the API
[429.40] handlers for the paths for the API for
[432.28] the API routes that are in that
[433.88] document. Which is cool, but then we
[435.76] eventually I eventually migrated that to
[438.88] just pure Flask. And then eventually
[441.12] migrated that to, uh, Fast API, which I
[444.08] believe is what it still is at the
[445.84] moment. Um, okay. So, it's the first 2
[449.04] weeks, and my primary focus is to build
[452.84] sort of what I promised in the
[454.20] interview, which is this web app that's
[456.36] going to be a broker for the platform,
[459.36] and is going to allow self-service
[461.96] provisioning of load balancing in
[464.16] Elastic. So, like I mentioned earlier, I
[466.56] started with this library called
[468.08] connection, which took an open API
[469.80] document, turned that into routes. But,
[472.00] I'm going to just go with
[473.96] what it ended up as, which is a fast API
[476.48] app. Let's just say we've got fast API
[478.88] here, and then we've got
[482.24] a worker, and then we have a database,
[485.96] which was DynamoDB. Oh, that's annoying.
[489.12] And we would have a client making
[491.84] requests. That's why that's a fast API.
[494.64] The client would say, "Hey, please
[496.68] provision something for me." And the web
[499.32] worker wouldn't do it itself. It would
[501.20] actually send that over SQS. It would
[505.00] drop the task details into SQS.
[508.40] And the worker would then handle that.
[511.40] So, what does a provisioning task
[513.44] actually look like?
[515.56] It's something like creating
[518.68] DNS records somewhere, maybe creating a
[522.88] CloudFront distribution, maybe creating
[527.12] some API calls. And this would be the
[531.28] provisioning task that the worker would
[533.52] do asynchronously, while the web and
[537.04] client would wait for it to be completed
[539.52] essentially. So, the client's polling
[541.28] continuously to say, "Is it ready? Is it
[543.88] ready?" And when it is completed, the
[546.04] worker writes it to the database, the
[548.40] web server checks the status, and then
[550.96] responds saying, "Yes, it's finished."
[552.92] Or it'll say that something went wrong
[555.20] and there was an error.
[556.48] So, then we can sort of encapsulate this
[558.72] as the open service broker that I built.
[563.12] Pretty straightforward.
[565.48] Um to be honest, there's not much more
[567.40] to this, but we're going to go and talk
[570.76] about some of the more complicated bits
[573.04] in just a second, and I will directly
[575.00] link to this as well. So, we got this
[577.16] client requesting
[579.64] uh let's say "Please provision a load
[581.60] balancing." And that is essentially what
[583.72] they were asking for was some kind of
[586.12] load balancing somewhere in the edge
[588.64] infrastructure of Atlassian to allow
[590.52] traffic to go to their service. So,
[593.44] that's a good uh demarcation point to
[596.12] start talking about the next thing that
[598.48] I sort of built.
[599.96] And I built it through necessity
[602.84] of Essentially, I began to understand
[606.60] and unravel the requirements more as I
[609.28] went along. One of the architects had
[611.76] this idea to replace the load balancers
[615.52] at Atlassian, which were enterprise load
[618.12] balancers that had licensing costs, with
[621.16] a open-source cloud-native sort of
[624.44] commodity proxy. And the tech that we
[626.60] chose for that was Envoy proxy. You may
[629.20] be familiar with Envoy proxy. If you're
[631.12] not, then it's very similar to something
[633.72] like Nginx, but perhaps more modern than
[637.68] Nginx. Um you can take a look at its,
[640.96] you know, uh what's what's great about
[642.64] it if you want. You can just read
[644.00] through like why why choose Envoy, blah
[646.24] blah blah. But essentially, we wanted
[647.82] [clears throat] to replace the
[648.76] enterprise load balancers we had, make
[650.52] them self-service, so that devs
[652.68] effectively didn't have to talk to us to
[655.00] go set up their load balancing. So,
[657.72] Envoy has an API that allows you to
[662.12] configure it dynamically. Being able to
[664.80] reload the configuration at run time
[666.72] means that you can deploy a whole bunch
[668.96] of proxies and have them sit there
[671.24] running all the time.
[672.88] And then when someone needs different
[674.44] configuration for their particular uh
[676.56] service, then they can push out a change
[679.60] through the provisioning task detailed
[681.76] here. And those changes should flow to
[685.04] the proxy somehow. And so now, that's a
[687.64] good time to talk about the Envoy
[690.80] management server that I built, which we
[692.60] called the Envoy control plane. And this
[695.60] was it's essentially quite similar
[700.12] uh to this.
[701.60] Yet again, we used a Fast API app. But
[704.64] this was slightly different actually.
[706.32] Let's go into a little bit of detail
[707.72] here. I'm just going to wing this
[709.12] because I should be able to wing it
[710.40] because I know it quite well. Uh this is
[712.20] actually a I open sourced this this
[715.04] software and I called it Sovereign. You
[716.60] can actually go find that on Bitbucket.
[718.76] It's it's a public repo at least for
[721.40] now. I don't know if that's going to be
[723.12] the case always.
[724.56] But essentially Sovereign runs a Fast
[726.28] API app. And some of the things that it
[729.00] takes in as
[731.12] uh configuration are templates
[735.32] and context. And so the app uh polls
[740.44] these. Uh it's obviously got like uh say
[744.32] let's just say this is the
[745.16] configuration. Okay, let's stick Now,
[748.16] so the templates might be particular
[752.40] resource types. And in Envoy, you've got
[755.08] stuff like clusters, routes, listeners.
[759.20] And let's just leave it at that for the
[760.92] moment. You'd have these kind of
[763.20] templates. And so when this when this
[767.04] management server loads up, it'll read
[769.04] in these templates in the context and
[770.76] make these available as APIs for the uh
[775.04] proxies. So then you can imagine let's
[778.28] just say we've got uh an Envoy here.
[782.56] It is going to request these things and
[785.92] Sovereign is going to respond by taking
[788.40] the context, putting it into the
[790.20] templates, and rendering out different
[792.52] content uh as the context changes. Now,
[795.40] where does the context come from? Well,
[797.68] this is part of this management server
[799.84] that is dynamic. So well, let's just uh
[802.76] let's just do a bit of flip around here.
[806.04] Put the context
[807.64] the context actually comes from this
[810.56] database, but we are requesting it from
[814.20] the broker. So, the we're we're
[816.12] requesting data from the broker and
[818.24] other sources, in fact. Let's just add
[820.56] another source here. Let's just say we
[822.16] have a little S3 bucket with some data,
[825.08] and maybe that data is changing over
[826.64] time. So, we take that data, it's
[828.32] dynamic, we feed that into the
[829.88] templates. The The templates have logic
[833.48] that spits out particular Envoy
[836.08] configuration, and then the proxy
[837.44] changes over time. So, what happens is
[840.16] we've got a client that's making a
[842.32] provisioning requests to our broker. The
[844.88] worker is doing some provisioning tasks,
[848.32] and then writing the new data to the
[850.12] database. Then the the management
[853.44] server, let's say. Stop this. Let's
[855.52] encapsulate this a little bit. The
[856.88] management server is then polling that
[858.60] data from various places and generating
[861.32] new configuration. That configuration
[863.60] hits the proxy, and then it starts doing
[866.32] different stuff. That is essentially the
[868.64] second part of what I built. So, we've
[870.56] got a broker, we've got a management
[871.92] server, we've got the client, we've got
[873.24] the proxy. Uh why did this detach?
[875.76] Anyway, so now we've sort of figured
[877.72] this stuff out.
[879.20] This is all at a very high level.
[881.64] >> [clears throat]
[881.76] >> So, we've got this created. Now we can
[884.08] sort of think more about more
[887.32] infrastructure type things. We've got
[889.68] this proxy, but how do we end up with
[891.80] this proxy? How does that actually get
[893.68] provisioned? What is it? Where does it
[895.16] live? Well, let's start with one thing,
[898.32] which is that these proxies,
[902.16] there's many many many of them, as you
[904.60] would expect, and they are provisioned
[906.80] by
[907.84] um
[908.68] they are provisioned by a CloudFormation
[911.84] template. This is an AWS thing that
[913.92] allows you to essentially do
[915.72] infrastructure as code, and it allows
[917.72] you to create resources in in AWS that
[921.64] you would normally create via the
[923.20] console if you were just uh uh let's say
[926.36] uh basic user. So, what kind of stuff do
[929.52] we create in here? Well, if we were to
[931.44] do this stuff from scratch, we'd
[933.00] probably have like a VPC and then we'd
[936.96] have uh you know, a subnet inside that
[940.00] VPC and maybe we'd have
[943.48] an internet gateway, maybe we'd have
[947.00] uh
[947.56] we'd all security group, maybe we'd have
[950.60] a key pair, maybe an IAM role.
[954.88] Um oh, of course we need to have the
[956.96] auto scaling group.
[958.92] Of course, that's what's going to be
[961.28] creating these
[963.60] EC2 instances.
[965.76] And well, the auto scaling group needs
[970.40] an AMI, doesn't it? Well, indeed it does
[972.72] need an AMI. IAM role has to be attached
[975.52] to
[976.72] uh must be attached to all these. The
[978.64] key pair goes on on the these. Security
[981.68] group is attached to to the
[984.32] this Well, it's probably attached to the
[986.24] auto scaling group to be fair. Well, the
[988.68] EC2 instances would inherit it from the
[990.68] from the ASG, blah blah blah. So, we've
[993.36] got all these like uh blocks of
[995.44] resources and stuff like that. Cool.
[997.36] Let's let's put these up put these up
[998.88] together, blah blah blah. Cool. So,
[1001.00] yeah, we've kind of got like a little
[1002.76] template going on here and it's creating
[1004.48] these proxies in many different regions.
[1008.28] Uh we might have we might have like
[1010.80] uh an NLB in here, a layer four proxy.
[1014.68] Maybe we'd have uh bit of maybe a bit of
[1017.36] ACM. Of course, these acronyms might
[1019.92] mean nothing to some people, but for
[1021.80] people that have used AWS, they would
[1023.48] know what these things are. And they
[1024.80] know it's not really that complicated.
[1026.96] It's like pretty basic building blocks
[1028.92] and this is what we created
[1031.40] uh
[1032.00] say 2,000 proxies,
[1034.36] uh something like 13 regions, blah blah
[1036.96] blah. Um and we also had a little bit of
[1039.64] route 53 records for other stuff. Now,
[1043.12] the AMI, it's not really provisioned by
[1046.08] the the template. It's more like it's
[1048.16] referenced by the template, isn't it?
[1050.20] So, that would bring us on to the next
[1052.00] piece of this thing that I built, which
[1054.96] is, well, we need to produce an AMI. We
[1057.52] need to produce a standard image for
[1059.92] these proxies, and it's going to include
[1061.64] all the important stuff in there. So,
[1063.56] how do we create this image for the
[1065.20] proxy? Well, in this case, we had uh
[1068.28] repository that was using HashiCorp
[1070.28] Packer, and
[1072.68] uh we had um
[1075.24] a Salt Stack
[1076.88] uh let's call it configuration.
[1078.76] And so, we would use Packer to um let's
[1082.52] say we'd have the EC Oh, we'd use the
[1085.60] EC2 provisioner. And so, we would create
[1088.92] an EC2 in like a dev account. We'd then
[1091.16] upload all of our Salt Stack
[1092.56] configuration. Salt Stack, by the way,
[1094.36] is very similar to Puppet, Ansible, and
[1096.84] Chef, in case you're not aware of what
[1098.32] those are. It is configuration
[1099.80] management tools, and that's a fancy way
[1102.16] of saying that I want to run I want to
[1105.08] install packages, put files, and run
[1108.16] services on a machine in a particular
[1110.44] way, in a particular order, and it
[1112.48] automates that process, makes that
[1114.96] process declarative for you. Well, not
[1117.12] for you, but it helps you to to make it
[1118.92] declarative. So, we created a little um
[1121.96] created a little EC2 live running EC2
[1124.64] here. We dump the config on there, we do
[1127.08] a provisioning step, and then we take
[1129.04] the
[1130.20] uh essentially turn this into an image,
[1132.44] like shut it down, uh whatever, snapshot
[1134.48] it, and turn it into an image. So, that
[1136.20] essentially would just produce this uh
[1138.92] AMI. Now, what was included in here?
[1140.68] Let's Let's say we can just uh we can
[1142.96] include a few things here. Let's just
[1144.64] say we had um we had states for for
[1147.80] Envoy. So, like let's say install,
[1150.16] configure,
[1151.84] uh let's say just install and configure
[1153.76] Envoy Uh
[1155.04] logging agents, security,
[1158.32] let's say slash hardening, network
[1159.84] tuning,
[1161.36] containers,
[1163.16] tracing. Oh, let's just say let's just
[1165.28] say observability agent there. And that
[1168.00] can cover I can cover logging, tracing,
[1170.88] metrics. So, that's essentially what's
[1172.92] going on here. Produces the AMI,
[1175.20] CloudFormation template takes this AMI
[1177.80] provisions these EC2s
[1180.16] EC2. And they're running with all this
[1182.80] stuff. And then when they when they get
[1184.92] provisioned, that's something that we
[1186.68] forgot here. There's parameters.
[1188.32] Parameters, bump that up, bump this up,
[1192.08] make it neat. So, we've got the
[1193.76] parameters and these at
[1197.00] runtime would pass in secrets and keys
[1200.56] and blah blah blah. And then these these
[1203.08] proxies would grab the resources, be
[1205.88] configured, and then they would be
[1207.44] running and accepting traffic. Boom,
[1209.60] that's it. Everything's done, working.
[1211.92] This was essentially the first two years
[1214.00] of working at Lyft. So, now when a
[1216.56] developer says, "I want to run my
[1219.24] service and I want it to be
[1221.40] I want it to be accessible on the
[1222.64] internet with all the fancy bells and
[1224.32] whistles and routing and advanced
[1225.84] stuff." We'd say, "Yes, no problem. Let
[1228.32] me just get that provisioned for you."
[1230.20] We
[1231.16] send off the provisioning task, we write
[1233.04] something to the database, we tell them
[1234.68] it's ready, then the management server,
[1237.36] it's the
[1239.08] broker says, "What's the current state
[1242.08] of things?" Takes that data, plus other
[1244.52] data, puts it into the templates,
[1246.36] creates resources out of those
[1248.32] templates, gives them to Envoy on when
[1250.52] it requests them. And this was all
[1253.12] pre-provisioned.
[1255.08] That's long-lived infrastructure with
[1257.08] CloudFormation. And the CloudFormation
[1258.92] is relying on an AMI that it can use to
[1261.88] provision those images, those machines.
[1263.92] So, yeah, that is probably the first 24
[1266.16] months. So, what was next after this?
[1268.24] So, this was the foundation of our team,
[1270.68] essentially the product that we were
[1272.08] going forward with, um which is uh
[1274.96] centralized load balancing managed by
[1277.64] our team, and all of the features that
[1280.08] we provided to our customers would live
[1282.92] in logic defined in these templates.
[1285.40] We've now laid the foundation for the
[1287.40] team. We've got proxy infrastructure
[1289.28] that's reacting dynamically to services
[1292.48] that are being deployed with different
[1294.08] configurations over time. What was next
[1296.20] after that point? The big thing after
[1298.12] that was taking some of the larger
[1300.88] products and making it possible for them
[1303.60] to use this platform component. That was
[1306.56] one big part, and the second big part
[1308.64] was migrating all of the microservices
[1311.64] within Atlassian to use this. And that
[1313.96] was relatively easier because we could
[1316.72] enforce that through the platform.
[1318.76] Essentially, what that means is that the
[1320.80] platform was previously providing very
[1323.24] basic load balancing to every service.
[1325.32] And they forced a switch to where you
[1328.80] could no longer expose your service
[1330.64] publicly through their load balancer,
[1332.40] which is too basic, and you had to go
[1334.20] through our centralized load balancing
[1336.48] infrastructure and to explicitly
[1338.80] configure it as a way of signaling your
[1341.24] intention for that service to be
[1343.44] publicly accessible. Whereas previously,
[1346.36] it could have just been maybe accidental
[1348.80] that your service was public and not
[1350.80] very well protected. So, that was the
[1352.68] big major push. We got products like
[1355.72] Jira, Confluence, Bitbucket, Status
[1358.08] Page, and many others behind this edge
[1361.08] infrastructure. And then, what was after
[1363.44] that? Well, now we can sort of talk more
[1365.68] about Let's say we can talk more about
[1368.44] the uh the Envoy-based product that we
[1371.92] had here. So, this particular thing,
[1374.76] we've got this groundwork of being able
[1377.04] to take basic inputs from a a developer
[1380.68] and to turn that into templated
[1383.40] configuration. Now, Envoy has a lot of
[1386.44] configuration. It has a lot of stuff you
[1389.32] can configure. Let's just look at the
[1391.56] routes, for example. Let's look at the
[1393.48] virtual host, for example. You can
[1395.36] configure what domains to accept traffic
[1397.28] on. Pretty basic. You can do routing.
[1399.08] Sort of basic, but once you delve into
[1401.48] how you can do this, it gets pretty
[1403.28] complicated pretty quickly. You can
[1405.08] match on different things. You can route
[1407.04] it in different ways. You can do direct
[1409.04] responses. do redirects, blah, blah,
[1411.16] blah. You can add and remove headers. I
[1414.08] guess I guess you could say that's
[1415.48] pretty standard, but you can also
[1417.08] choose, for example, when you're
[1419.20] configuring a route action, you can also
[1420.84] choose to send to any cluster that's on
[1424.68] the proxy. So, then if I have a thousand
[1427.64] devs, or a thousand services, and they
[1430.24] each have their own cluster, and any
[1432.28] route can send to any cluster, well, it
[1434.92] sort of brings up this point of well,
[1436.76] this
[1437.88] data here needs to be validating that
[1441.28] and abstracting that, and so on and so
[1445.52] forth. So, there was definitely a
[1447.68] concentration of a lot of the
[1449.12] development work around this logic here,
[1451.60] making sure it was validated here in
[1453.84] terms of the parameters were validated
[1456.08] such that when those parameters were run
[1458.72] through the logic in these in these
[1461.16] resources, that it would produce valid
[1463.88] resources. Pretty standard, I suppose
[1465.84] you could say. I don't know. Maybe I do
[1467.68] feel like I have the curse of knowledge.
[1469.56] Um and that this stuff seems easier to
[1472.12] me now because I I've done so much with
[1474.28] it. Uh but there's a lot. There's a lot
[1476.32] in here. And if we go into, uh for
[1478.60] example, extensions, there's a lot of
[1480.80] extensions that can be applied to a
[1483.76] listener or a or a cluster. For example,
[1486.56] you might have, uh where is it? You've
[1488.88] got, uh network filters here. You've got
[1491.44] all kinds of network filters. And a big
[1493.76] one that we obviously used was a HTTP
[1496.64] connection manager, where you could
[1498.60] configure routing and how to handle
[1501.68] proxies and web sockets and all this
[1504.60] stuff. And then, if we go a little bit
[1506.40] before that, there's also things like
[1508.64] external processing and external
[1511.24] authorization. And this sort of brings
[1513.84] us to Oh, let's say something that
[1516.44] happened next. So, I did briefly mention
[1518.40] that some of the big parts after
[1519.68] building this was to migrate big
[1521.72] products onto Let's assume that's all
[1523.64] finished. It took It took some time. It
[1525.88] took a couple years because there were
[1527.68] many features that needed to be built
[1529.28] out here and and wherever else in order
[1532.20] to support the larger products and their
[1534.36] special cases to work on
[1537.88] what's effectively a generic
[1539.72] multi-tenanted platform. So, let's just
[1541.52] assume that they're all migrated. Then,
[1542.88] we have more features that we want to
[1545.36] add. I did sort of allude to like we
[1547.44] have this We have this groundwork. We
[1549.36] have this dynamic configuration. What
[1552.48] I'm trying to say is that we we created
[1554.84] opportunity. We created opportunity to
[1557.24] centralize logic and to handle concerns
[1561.76] early in the chain of requests. What I
[1564.56] mean by that is a customer, let's just
[1567.12] make a smiley customer. And customer is
[1570.24] someone that's using our cloud products
[1572.32] or Atlassian cloud products. They are
[1574.52] hitting the
[1576.16] Let's just say they're hitting an NLB
[1577.64] first and that's then being proxied to
[1579.88] these boys. Yes? If we can deal with the
[1582.88] problems here before they reach a
[1584.96] service,
[1586.32] let's say and let's give it a square.
[1588.20] Let's call it a back-end service, you
[1590.16] know. So, the requests are flowing in
[1591.96] from the customer to the proxies and to
[1594.00] the Pretty standard stuff. If we can
[1595.88] deal with certain concerns here before
[1599.04] it reaches here, we save a lot of time,
[1601.72] we save some money, which is and it
[1604.04] saves the customer time. It's great for
[1605.72] everyone, really. Um
[1607.52] and one of those things Now, this is
[1609.28] where the the diagram becomes
[1611.04] complicated, so let's move off to the
[1613.16] side. Let's just copy a few of these.
[1615.40] Let's grab
[1616.68] three things
[1618.12] move over to the side. We've got the
[1619.52] customer talking to the proxy and the
[1621.56] proxy is talking to back end. Of course,
[1624.28] the request comes back up and back out
[1626.44] to the customer. Fine and dandy. Yes,
[1628.52] this is a this is a proxy. Whatever,
[1630.60] there's no surprises here. Now, without
[1632.80] with with the products that Elysium
[1635.24] runs, there's all kinds of stuff that
[1637.88] needs to happen like authentication for
[1639.60] example or authorization or
[1643.36] DDoS protection or rate limiting or
[1646.36] access logs. All this kinds of stuff
[1648.60] that needs to happen and it's just turns
[1651.04] out that we can deal with them here
[1652.80] instead of on a bazillion bazillion back
[1657.08] end services. Just imagine there are a
[1660.12] bazillion bazillion of these. Just
[1663.60] zillions upon zillions. See Daisy. Just
[1667.04] zillions and zillions. They're like
[1668.68] gazillion. Now, can you imagine if a
[1670.72] thousand dev teams needed to deal with
[1673.56] all this stuff plus more on their own
[1676.36] service? It would be a tremendous waste
[1679.48] of money for the company. It would slow
[1681.08] down features. The customer wouldn't get
[1683.16] their features when they need them and
[1685.04] stuff is already hard enough to deliver
[1687.16] as it is. Thus, the platform and
[1690.28] centralized management of resources and
[1692.48] centralized
[1693.88] implementation of these features. So,
[1696.08] how how were some of these things
[1697.80] implemented? Well, DDoS protection was
[1699.88] really provided by
[1702.12] CloudFront. That was
[1704.32] that was
[1705.28] spearheaded by a colleague of mine who
[1707.88] is very smart and conscientious. And
[1710.68] essentially, let's make this a bit more
[1713.12] accurate. Let's just say let's get rid
[1714.92] of these. There's an NLB here. Oh, blah
[1717.32] blah blah blah blah. And of course, it's
[1719.60] two-way. So, that's one way that we can
[1721.72] take care of that concern for these back
[1723.84] end services. Great, we've solved solved
[1725.92] the concern for that. Fantastic. These
[1727.72] others, well, access logs, what we can
[1730.92] do is something like we can use these
[1733.44] network filters. Yes, we use the network
[1735.92] filters. For example, in the HCM, we
[1738.76] have
[1743.44] Where are the access logs? Access log.
[1745.80] Now, remember, all of this configuration
[1748.28] is dynamic. It's all dynamic and it is
[1751.44] created by templates which abstract away
[1755.36] the resource configuration from the
[1757.32] developer who wants to configure it.
[1759.16] They provide simple parameters. Those
[1761.12] parameters are then validated and then
[1762.84] they are fed into the template as
[1764.48] context so that we produce the correct
[1767.20] template. That means that
[1769.92] they send us a little bit of JSON and we
[1772.28] set up this whole thing for them with
[1774.36] all the access logging and blah blah
[1776.20] blah, whatever. So, that is done, in
[1778.08] fact, inside the proxy, natively.
[1781.16] Fantastic. Some of these things,
[1782.92] however, a little bit more complicated.
[1784.44] These things, we need to use a sidecar
[1787.00] model where Envoy is talking out the
[1788.52] side and then these are their own
[1791.32] services running locally on the on the
[1793.48] proxy. So, these would be like
[1796.52] containers, essentially. We've got this
[1798.16] sidecar model and those sidecars, some
[1801.04] of them were contributed by other teams
[1803.56] and some of them were created by me and
[1805.68] our team. The authentication and the
[1807.36] authentication sidecar was created by
[1809.04] me, written, of course, in the Lord's
[1812.36] language, Rust. Authorization was done
[1815.04] by another team and rate limiting was
[1816.56] done by another team. And so, they were
[1818.04] able to contribute these sidecars,
[1820.08] which, by the way, were set up and
[1823.56] were downloaded and configured onto the
[1826.08] AMI by this provisioning AMI
[1828.96] provisioning flow. Great. So, now we
[1831.60] have a programmable proxy with sidecars
[1835.28] that have their own separate logic from
[1837.48] the proxy and they, too, can actually
[1840.00] receive configuration, which is dynamic
[1843.00] over the wire locally and
[1846.08] and make it even more program. So, we're
[1848.16] solving all these concerns before they
[1850.36] hit these
[1851.84] these back ends and in very very little
[1854.16] time. So, that was
[1855.92] essentially that is some of the stuff I
[1858.04] worked on after migrations and blah blah
[1860.44] blah. Yay. What I do after that? With
[1863.04] this big blob rid of this mess. So, then
[1865.88] we had some non-technical requirements
[1868.24] come through. More compliance
[1871.00] and things like that. And that effort
[1873.20] was very tedious and boring for me
[1875.72] personally. It didn't involve building
[1877.60] new stuff. It involved taking all of
[1879.60] this, making sure that it was compliance
[1882.40] for in certain ways. Very bored boring
[1886.20] checklist ticking work. Blah blah blah.
[1889.20] So, I said earlier that I would also go
[1890.88] over some of the non-technical things
[1892.36] that I had to go through while working
[1894.16] at Atlassian. Obviously, all of that
[1895.56] stuff is sort of high-level technical
[1897.68] stuff that I just showed. What was some
[1900.52] of the other stuff that I went through
[1902.56] during my eight-year slog at Atlassian?
[1905.12] The first few things to come that come
[1907.12] to mind is that I have grown
[1910.20] tremendously in my diplomacy skills,
[1914.68] conflict avoidance, probably conflict
[1917.44] resolution as well. Being able to
[1919.92] persuade, propose ideas, being able to
[1922.80] teach, educate, and mentor. These are
[1925.04] the non-technical things that you
[1926.44] probably don't hear a lot about. But
[1929.12] after Another thing is that the ability
[1931.68] to maintain things, maintain software
[1935.24] and systems, to see where the cracks
[1937.92] show up and to build things so that
[1941.24] those cracks don't show up as or at
[1943.48] least to make them show up late as
[1945.12] possible. That's definitely something
[1946.52] that I picked up. Let's just talk about
[1948.20] that maintenance for a sec. I noticed
[1950.56] over the eight years that I was there,
[1952.24] when I built these apps, these
[1955.16] services, that there's obviously that at
[1957.92] the very start there's the requirement
[1960.24] to onboard people and write
[1961.72] documentation and train people so that
[1964.04] they understand how things work, know
[1966.56] how to contribute to them, and debug
[1968.48] them. So that when they become when they
[1970.32] go on call, they know where to look,
[1972.80] what could go wrong, where do things
[1974.96] break essentially. So, you know, that's
[1977.64] whether that's knowing what kind of what
[1980.40] particular log messages mean, what sort
[1982.52] of metrics to check when something is
[1985.04] going wrong and what those metrics could
[1987.16] allude to, how to resolve those
[1990.16] um you know, particular expected
[1992.40] problems if they're not automated away.
[1994.72] Um and this could be like, you know,
[1996.88] Amazon could have an outage and the
[1998.80] database isn't access for example. What
[2000.64] do you do in that case? What if SQS
[2002.80] stops working and you can't do any
[2004.28] provisioning tasks? What how what impact
[2006.52] does that have on the services that need
[2008.16] to provision the resources? And how do
[2009.88] you resolve um
[2011.48] What happens if an if a proxy receives
[2013.76] bad configuration? What if it receives
[2015.52] configuration that's valid, but that
[2017.60] destroys the traffic that's flowing
[2019.36] through? How do you pick up on those?
[2021.24] What do you check, etc. etc. So there's
[2023.48] obviously a lot of that at the start
[2025.24] when you build something. There's a lot
[2026.56] of that at the start. But the thing
[2028.44] that's more difficult is over time
[2030.96] people come and go. People get hired.
[2033.24] People get people leave for other jobs
[2035.36] and whatnot. And so you get you have to
[2037.44] do that onboarding again obviously. But
[2039.36] you should have more people that are
[2041.04] able to do that onboarding collectively.
[2042.80] But then you sort of bring in new
[2044.24] opinions. People look at an existing
[2046.24] codebase and they want to change things.
[2048.88] They want to make it better, and so on
[2050.24] and so forth. And so they do that. And
[2052.96] change ends There's I I suppose there's
[2055.80] this concept of churn in the codebase.
[2058.04] The area that churns, it's sort of it
[2060.20] becomes predictable where all the churn
[2062.44] is going to be
[2064.04] at a certain stage. And once you notice
[2066.56] that there is some churn, it's sort of a
[2069.12] a smell. It is it's an indication that
[2072.20] that part of the service or project is
[2075.40] going to keep increasing in size or
[2078.40] complexity. And something there needs to
[2081.24] happen. Something needs to be done to
[2083.04] avoid that mess. It's just just how
[2085.36] software goes, I suppose. It'll be
[2087.48] interesting with all these
[2089.92] vibe coded apps and AI assisted apps to
[2092.52] see how we handle that. When we have
[2094.56] people that are not really familiar with
[2096.60] what they've created, and the
[2098.52] maintenance burdens appear. They don't
[2100.56] appear at the beginning. There's just
[2101.92] not enough going through. It hasn't been
[2103.68] around for long enough. There hasn't
[2105.00] been enough changes. Building something
[2106.60] is easy. Changing it and making sure
[2108.40] that it you can still change it over
[2109.92] time is difficult. Because as you change
[2112.04] things, it slowly becomes harder to
[2114.72] change. Things start to get coupled, and
[2116.88] all of a sudden when you change
[2118.16] something in one area, it affects
[2119.68] another, and you have to deal with the
[2120.88] task of detangling something. And you
[2122.36] might be able to find these areas quite
[2124.16] quickly, get an LLM to perform the
[2126.76] detangling for you. I think that's If we
[2128.96] can do that, that's fantastic. But I
[2130.80] don't want to be too optimistic just in
[2132.68] case. So, there's that on That's my
[2135.40] opinion on the maintenance side of
[2136.80] things. The next thing I want to talk
[2138.56] about is when I mentioned diplomacy,
[2141.52] what I'm really trying to say is that I
[2143.92] was exposed to different types of
[2146.00] managers and colleagues over time. And
[2148.72] everyone has different personalities and
[2150.28] styles of working. And because I was
[2152.04] exposed to so many different types, I
[2154.16] experienced conflicts with certain
[2156.44] people. And even though I had conflicts,
[2159.00] there's still people that I respect.
[2160.84] It's just something that happens when
[2163.08] you when your personality doesn't mix
[2165.16] with their personality. And that's just
[2166.72] something that's a bit inevitable. And I
[2168.88] think that the only thing you can really
[2170.84] do in those situations is to try to have
[2173.64] the self-awareness and the awareness of
[2175.80] the other person and the, I suppose,
[2178.28] understanding of psychology and and how
[2180.64] people work to an extent, so that you
[2183.08] can be responsible for that difference
[2185.36] and the potential for conflict, and to
[2188.24] handle it effective to to anticipate the
[2191.00] conflict that's going to arise and and
[2193.32] to do something to make the relationship
[2196.24] work. And maybe it's impossible. I don't
[2197.84] know. But that was definitely a source
[2199.52] of great stress and at [clears throat]
[2201.60] times it affected my performance. And so
[2205.84] I do think that because it affected my
[2208.88] performance that I took it quite
[2210.84] seriously and I learned and changed as a
[2213.44] result. So the next time that those
[2215.52] situations come around, I do firmly
[2218.28] believe that I'll be able to handle them
[2220.52] quite a lot better. And then some of the
[2222.84] other things, in fact one of the things
[2224.80] that I found quite challenging was
[2228.24] mentoring. And so I find it easy to help
[2231.28] people to point out areas where they
[2235.52] need understanding and to deliver that
[2238.60] understanding to them, to break down
[2240.76] complex things into simple terms so that
[2243.28] they can build a mental model of the
[2246.08] system that they're working on. I have
[2247.76] that ability. I'm quite good at that.
[2249.20] But mentoring is distinct from that. I
[2251.88] had an intern in the last year and I
[2254.16] will first say that the result of their
[2256.32] internship was that they got the highest
[2258.84] rating possible and it essentially
[2261.08] guarantees
[2262.64] an offer to work at a last year. The
[2264.72] project that they worked on was very
[2266.76] impressive and how they approached it
[2269.64] and and built it was very impressive.
[2271.52] And so that's why they got that
[2272.60] excellent rating. What I found
[2274.56] personally difficult was striking the
[2277.68] balance between It was essentially
[2280.32] striking the balance between how much
[2282.16] time I give to the mentee and what that
[2286.00] time would consist of, whether it's, you
[2288.12] know, I didn't I don't want to give them
[2289.52] answers to problems, but I don't want
[2291.88] them to get so stuck that they become
[2293.76] frustrated. I have no idea if I reached
[2296.20] that balance, but I suppose the results
[2298.32] speak for themselves. I I but I I don't
[2300.64] I don't I'm not sure if I can attribute
[2302.20] the results to me necessarily. The
[2304.12] intern was helped by some of my other
[2306.28] colleagues when in areas that I'm much
[2308.56] weaker in. So, they effectively got
[2311.04] subject matter experts in a few
[2314.04] different areas to contribute to their
[2316.20] success. But then they did the majority
[2318.92] of the legwork to actually build the
[2321.48] thing and to test it and to make design
[2324.00] decisions and stuff like that. And it
[2325.40] was very successful. But I still have
[2326.68] this lingering impression of feeling
[2328.84] that mentoring is difficult for me and
[2331.04] that I I don't have um a good way of um
[2335.08] figuring that out because I've never
[2336.68] been mentored myself. So, I don't really
[2338.96] know what to expect and what they do.
[2341.36] But I want to emphasize that that's a
[2343.64] very specific type of mentoring that I'm
[2345.28] not too sure about. Whereas training my
[2347.36] colleagues, getting them to understand,
[2349.60] working, you know, working through
[2351.08] problems with my colleagues, that was
[2352.76] that was essentially my bread and butter
[2354.64] during the last half of my employment.
[2356.48] You know, jumping on uh uh call and
[2359.32] going through stuff. Feedback that I got
[2361.44] from my colleagues all the time was that
[2362.88] I was always available to help and that
[2364.84] I could boil down hard topics into
[2366.80] something that was understandable, which
[2369.08] I'm pretty proud of. And I've been
[2371.32] yapping for a while. I think that covers
[2372.96] a quite a lot. If I remember more, I'll
[2374.84] probably just make a second video. Um
[2376.64] maybe maybe if people are interested, I
[2378.84] could actually go through and build some
[2380.32] of these things. I could actually go
[2381.72] through and build some of these things
[2382.92] from scratch on stream or just a video
[2385.24] uploaded to kind of show, I guess,
[2387.32] essentially what I made and maybe
[2388.68] recreate and sharpen my skills a little
[2390.56] bit more. Um maybe. I've got a lot of
[2392.64] stuff on my to-do list, so maybe maybe
[2394.56] not. It depends on the demand. Anyway,
[2395.92] I'm going to cut the video from here. If
[2397.92] you listened all the way through or to
[2399.72] portions, then thank you very much. I
[2401.68] hope it was interesting and enlightening
[2403.48] and whatever else. I'll catch you
[2405.56] around.
```
